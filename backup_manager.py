import os
import re
from datetime import datetime, date, timedelta
from typing import Callable

from drive_service import DriveService


class BackupManager:
    """
    Core backup sync logic — sliding window approach.

    Validation logic:
    ─────────────────
    Alerta de contagem insuficiente só é emitido quando já deveriam existir N backups,
    ou seja, quando o backup mais antigo encontrado tem mais de (N-1) dias.
    Se ainda estamos acumulando (início do uso), apenas informa o progresso.

    Remoção no Drive — sliding window:
    ───────────────────────────────────
    Após o upload do novo backup, remove APENAS o mais antigo se o total exceder N.
    Nunca remove em lote — sempre uma remoção por sincronização.
    Exemplo com N=3:
        Antes:  [D15, D16, D17]          (Drive)
        Upload: [D15, D16, D17, D18]     (N+1)
        Remove: [D16, D17, D18]          (remove D15 → volta para N)
    """

    def __init__(self, drive_svc: DriveService,
                 log_fn: Callable,
                 refresh_fn: Callable):
        self.drive   = drive_svc
        self.log     = log_fn
        self.refresh = refresh_fn

    # ── Public ────────────────────────────────────────────────────────────────
    def run_sync(self, cfg: dict, history: list, cancel_evt=None):
        backup_dir = cfg["backup_dir"]
        folder_pai = cfg["folder_pai"]
        cliente    = cfg["cliente"]
        qtd        = int(cfg.get("qtd_backups", 3))
        extensoes  = [e.strip().lstrip(".") for e in cfg.get("extensoes", ".sql").split(",")]

        self.log(f"Iniciando sincronização para '{cliente}'...", "INFO")

        # ── Step 1: Scan & sort local backups ──────────────────────────────
        local_files = self._scan_local(backup_dir, extensoes)
        if cancel_evt and cancel_evt.is_set():
            self.log("Sincronização cancelada.", "WARN")
            return
        if not local_files:
            self.log(f"Nenhum arquivo de backup encontrado em: {backup_dir}", "WARN")
            return

        local_files.sort(key=lambda f: f["sort_key"])
        self.log(f"{len(local_files)} arquivo(s) encontrado(s) localmente.", "INFO")

        # ── Step 2: Pick the last N ─────────────────────────────────────────
        last_n = local_files[-qtd:]

        # ── Step 3: Smart count validation ─────────────────────────────────
        self._validate_count(last_n, qtd)

        # ── Step 4: Ensure Drive folder structure ───────────────────────────
        self.log("Verificando estrutura de pastas no Drive...", "INFO")
        pai_id = self.drive.get_or_create_folder(folder_pai)
        if cancel_evt and cancel_evt.is_set():
            self.log("Sincronização cancelada.", "WARN")
            return
        if not pai_id:
            self.log("Não foi possível acessar/criar a pasta pai no Drive.", "ERROR")
            return

        cli_id = self.drive.get_or_create_folder(cliente, pai_id)
        if cancel_evt and cancel_evt.is_set():
            self.log("Sincronização cancelada.", "WARN")
            return
        if not cli_id:
            self.log("Não foi possível acessar/criar a pasta do cliente no Drive.", "ERROR")
            return

        self.log(f"Pasta Drive: {folder_pai}/{cliente}", "OK")

        # ── Step 5: Upload only what's missing on Drive ─────────────────────
        drive_files  = self.drive.list_files_in_folder(cli_id)
        drive_names  = {f["name"]: f["id"] for f in drive_files}
        uploaded_any = False

        for f in last_n:
            if cancel_evt and cancel_evt.is_set():
                self.log("Sincronização cancelada.", "WARN")
                return
            if f["name"] not in drive_names:
                self.log(f"Enviando: {f['name']}...", "INFO")
                ok = self.drive.upload_file(f["path"], cli_id, cancel_evt=cancel_evt)
                self._record_history(history, f["name"], "OK" if ok else "ERROR")
                if cancel_evt and cancel_evt.is_set():
                    self.log("Sincronização cancelada.", "WARN")
                    return
                if ok:
                    uploaded_any = True
            else:
                self.log(f"Já existe no Drive: {f['name']}", "INFO")

        # ── Step 6: Sliding window — remove ONLY the oldest if over limit ───
        if uploaded_any:
            if cancel_evt and cancel_evt.is_set():
                self.log("Sincronização cancelada.", "WARN")
                return
            drive_files = self.drive.list_files_in_folder(cli_id)
            # Sort by the date embedded in the filename (same logic as local)
            drive_files.sort(key=lambda f: self._extract_sort_key(f["name"]))

            if len(drive_files) > qtd:
                oldest = drive_files[0]
                self.log(
                    f"Janela deslizante: removendo o mais antigo → {oldest['name']}",
                    "WARN"
                )
                self.drive.delete_file(oldest["id"], oldest["name"])

                # Safety: if somehow still over limit (e.g. manual uploads), warn only
                drive_files = self.drive.list_files_in_folder(cli_id)
                if len(drive_files) > qtd:
                    self.log(
                        f"Drive contém {len(drive_files)} arquivos (limite {qtd}). "
                        "Remova manualmente os excedentes se necessário.",
                        "WARN"
                    )

        # ── Step 7: Final report ────────────────────────────────────────────
        remaining = self.drive.list_files_in_folder(cli_id)
        remaining.sort(key=lambda f: self._extract_sort_key(f["name"]))

        self.log(
            f"Sincronização concluída. Drive contém {len(remaining)} backup(s):",
            "OK"
        )
        for f in remaining:
            self.log(f"  → {f['name']}", "INFO")

        self.refresh(history)

    # ── Validation ────────────────────────────────────────────────────────────
    def _validate_count(self, sorted_files: list, qtd: int):
        """
        Only alert if we SHOULD have N backups by now.

        Rule: if the oldest available backup was generated more than (N-1) days ago,
        all N backups should have been created — missing ones are a real problem.

        If we're still within the N-day accumulation window, just show progress.
        """
        count = len(sorted_files)

        if count >= qtd:
            self.log(f"Contagem OK: {count} backup(s) disponível(is).", "OK")
            return

        if count == 0:
            return  # already handled above

        # Try to extract the date of the OLDEST file
        oldest_date = self._extract_date(sorted_files[0]["name"])
        today       = date.today()

        if oldest_date is None:
            # Can't determine date from filename — use file modification time as fallback
            try:
                mtime = os.path.getmtime(sorted_files[0]["path"])
                oldest_date = datetime.fromtimestamp(mtime).date()
            except Exception:
                oldest_date = today

        days_since_first = (today - oldest_date).days

        if days_since_first >= qtd - 1:
            # Enough time has passed → this IS an error
            self.log(
                f"ERRO: Apenas {count} de {qtd} backup(s) encontrados localmente. "
                f"O primeiro backup tem {days_since_first} dia(s) — "
                f"os demais podem não ter sido gerados. Verifique o sistema de backup.",
                "ERROR"
            )
        else:
            # Still accumulating — completely normal
            self.log(
                f"Acumulando backups: {count} de {qtd} "
                f"(dia {days_since_first + 1} de {qtd} — ainda dentro do período inicial).",
                "INFO"
            )

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _scan_local(self, folder: str, extensions: list) -> list[dict]:
        result = []
        try:
            for fname in os.listdir(folder):
                ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
                if ext in [e.lower() for e in extensions]:
                    fpath = os.path.join(folder, fname)
                    if os.path.isfile(fpath):
                        result.append({
                            "name":     fname,
                            "path":     fpath,
                            "sort_key": self._extract_sort_key(fname),
                            "size":     os.path.getsize(fpath),
                        })
        except Exception as e:
            self.log(f"Erro ao escanear pasta local: {e}", "ERROR")
        return result

    @staticmethod
    def _extract_sort_key(fname: str) -> str:
        """
        Extract YYYYMMDD[HHMM] from filename for chronological sorting.
        'BACKUP 20260315 2200.sql' → '202603152200'
        'BACKUP 20260315.sql'      → '20260315'
        Falls back to the raw filename string.
        """
        m = re.search(r"(\d{8})[_\s-]?(\d{4})", fname)
        if m:
            return f"{m.group(1)}{m.group(2)}"
        m = re.search(r"(\d{8})", fname)
        if m:
            return m.group(1)
        return fname

    @staticmethod
    def _extract_date(fname: str) -> date | None:
        """Extract a date object from YYYYMMDD pattern in filename."""
        m = re.search(r"(\d{4})(\d{2})(\d{2})", fname)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass
        return None

    @staticmethod
    def _record_history(history: list, filename: str, status: str):
        history.append({
            "filename": filename,
            "datetime": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "status":   status,
        })
        if len(history) > 200:
            del history[:-200]
