"""
BackupManager v2
────────────────
Dois modos:

  ROTAÇÃO  (modo="rotacao")
    Lógica atual intacta — sliding window, N mais recentes, validação de contagem.

  ESPELHO  (modo="espelho")
    Envia para o Drive todos os arquivos locais que ainda não existem lá.
    Nunca remove nada do Drive.
    Filtra por extensão se definida; caso contrário envia tudo.
    Estrutura flat: Pasta Pai → Cliente → [arquivos]
"""

import os
import re
from datetime import datetime, date
from typing import Callable

from drive_service import DriveService


class BackupManager:
    def __init__(self, drive_svc: DriveService,
                 log_fn: Callable,
                 refresh_fn: Callable):
        self.drive   = drive_svc
        self.log     = log_fn
        self.refresh = refresh_fn

    # ═══════════════════════════════════════════════════════════════════════════
    #  Entry point — roteia pelo modo do perfil
    # ═══════════════════════════════════════════════════════════════════════════
    def run_sync(self, profile: dict, history: list, cancel_evt=None):
        modo = profile.get("modo", "rotacao")
        nome = profile.get("nome") or profile.get("cliente", "?")

        self.log(f"── Perfil: {nome} [{modo.upper()}] ──", "INFO")

        if modo == "espelho":
            self._sync_espelho(profile, history, cancel_evt=cancel_evt)
        else:
            self._sync_rotacao(profile, history, cancel_evt=cancel_evt)

    # ═══════════════════════════════════════════════════════════════════════════
    #  MODO ROTAÇÃO  (lógica original — sem alteração)
    # ═══════════════════════════════════════════════════════════════════════════
    def _sync_rotacao(self, cfg: dict, history: list, cancel_evt=None):
        backup_dir = cfg["backup_dir"]
        folder_pai = cfg["folder_pai"]
        cliente    = cfg["cliente"]
        qtd        = int(cfg.get("qtd_backups", 3))
        extensoes  = [e.strip().lstrip(".") for e in cfg.get("extensoes", ".sql").split(",")]

        if cancel_evt and cancel_evt.is_set():
            return
        local_files = self._scan_local(backup_dir, extensoes)
        if not local_files:
            self.log(f"Nenhum arquivo encontrado em: {backup_dir}", "WARN")
            return

        local_files.sort(key=lambda f: f["sort_key"])
        self.log(f"{len(local_files)} arquivo(s) encontrado(s) localmente.", "INFO")

        last_n = local_files[-qtd:]
        self._validate_count(last_n, qtd)

        pai_id  = self._ensure_folder(folder_pai, None)
        if not pai_id: return
        cli_id  = self._ensure_folder(cliente, pai_id)
        if not cli_id: return
        dest_id = self._ensure_folder(cfg['nome'], cli_id)
        if not dest_id: return
        self.log(f"Pasta Drive: {folder_pai}/{cliente}/{cfg['nome']}", "OK")

        wanted_names = [f["name"] for f in last_n]
        drive_names  = self.drive.find_files_in_folder_by_names(dest_id, wanted_names)
        uploaded_any = False

        for f in last_n:
            if cancel_evt and cancel_evt.is_set():
                return
            if f["name"] not in drive_names:
                ok = self.drive.upload_file(f["path"], dest_id, cancel_evt=cancel_evt)
                self._record(history, f["name"], cfg.get("nome",""), "OK" if ok else "ERROR")
                if ok:
                    uploaded_any = True
            else:
                self.log(f"Já existe no Drive: {f['name']}", "INFO")

        # Sliding window — remove apenas o mais antigo se ultrapassar o limite
        if uploaded_any:
            if cancel_evt and cancel_evt.is_set():
                return
            drive_files = self.drive.list_files_in_folder(dest_id)
            drive_files.sort(key=lambda f: self._extract_sort_key(f["name"]))
            if len(drive_files) > qtd:
                oldest = drive_files[0]
                self.log(f"Janela deslizante: removendo → {oldest['name']}", "WARN")
                self.drive.delete_file(oldest["id"], oldest["name"])
                drive_files = self.drive.list_files_in_folder(dest_id)
                if len(drive_files) > qtd:
                    self.log(f"Drive contém {len(drive_files)} arquivos (limite {qtd}). "
                             "Remova manualmente os excedentes se necessário.", "WARN")

        remaining = self.drive.list_files_in_folder(dest_id)
        remaining.sort(key=lambda f: self._extract_sort_key(f["name"]))
        self.log(f"Concluído. Drive contém {len(remaining)} backup(s):", "OK")
        for f in remaining:
            self.log(f"  → {f['name']}", "INFO")

        self.refresh(history)

    # ═══════════════════════════════════════════════════════════════════════════
    #  MODO ESPELHO  — nunca remove do Drive; subpastas opcionais (recursivo)
    # ═══════════════════════════════════════════════════════════════════════════
    def _sync_espelho(self, cfg: dict, history: list, cancel_evt=None):
        backup_dir  = cfg["backup_dir"]
        folder_pai  = cfg["folder_pai"]
        cliente     = cfg["cliente"]
        recursivo   = cfg.get("recursivo", False)
        ext_raw     = cfg.get("extensoes", "").strip()

        extensoes = (
            [e.strip().lstrip(".").lower() for e in ext_raw.split(",") if e.strip()]
            if ext_raw else []
        )
        all_ext = not extensoes

        # Garante estrutura base no Drive: Pai / Cliente / Nome-do-perfil
        pai_id  = self._ensure_folder(folder_pai, None)
        if not pai_id: return
        cli_id  = self._ensure_folder(cliente, pai_id)
        if not cli_id: return
        dest_id = self._ensure_folder(cfg["nome"], cli_id)
        if not dest_id: return
        self.log(f"Pasta Drive: {folder_pai}/{cliente}/{cfg['nome']}", "OK")

        # Sincroniza recursivamente a partir da pasta raiz
        drive_cache = {}
        total_new, total_ok = self._espelho_dir(
            local_dir   = backup_dir,
            drive_id    = dest_id,
            extensoes   = extensoes,
            all_ext     = all_ext,
            recursivo   = recursivo,
            history     = history,
            nome_perfil = cfg.get("nome", ""),
            rel_path    = "",
            cancel_evt  = cancel_evt,
            drive_cache = drive_cache,
        )

        self.log(
            f"Espelho concluído: {total_ok}/{total_new} arquivo(s) enviado(s).",
            "OK" if total_ok == total_new else "WARN"
        )
        self.refresh(history)

    def _espelho_dir(self, local_dir: str, drive_id: str,
                     extensoes: list, all_ext: bool, recursivo: bool,
                     history: list, nome_perfil: str, rel_path: str,
                     cancel_evt=None, drive_cache=None) -> tuple[int, int]:
        """
        Sincroniza um diretório local com uma pasta do Drive.
        Retorna (novos_encontrados, enviados_com_sucesso).
        Se recursivo=True, desce em cada subpasta criando o espelho no Drive.
        """
        total_new = 0
        total_ok  = 0

        if cancel_evt and cancel_evt.is_set():
            return 0, 0
        try:
            entries = os.listdir(local_dir)
        except Exception as e:
            self.log(f"Erro ao listar {local_dir}: {e}", "ERROR")
            return 0, 0

        # ── Arquivos desta pasta ──────────────────────────────────────────────
        local_files = []
        for name in entries:
            fpath = os.path.join(local_dir, name)
            if not os.path.isfile(fpath):
                continue
            if not all_ext:
                ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                if ext not in extensoes:
                    continue
            local_files.append({"name": name, "path": fpath})

        if local_files:
            if drive_cache is None:
                drive_cache = {}
            drive_names = drive_cache.get(drive_id)
            if drive_names is None:
                drive_files = self.drive.list_files_in_folder(drive_id)
                drive_names = {f["name"] for f in drive_files}
                drive_cache[drive_id] = drive_names

            new_files = [f for f in local_files if f["name"] not in drive_names]
            already   = len(local_files) - len(new_files)

            display = f"/{rel_path}" if rel_path else " (raiz)"
            if already:
                self.log(f"{already} arquivo(s) já no Drive{display} — pulando.", "INFO")
            if new_files:
                self.log(f"Enviando {len(new_files)} arquivo(s) novo(s){display}...", "INFO")

            total_new += len(new_files)
            for f in new_files:
                if cancel_evt and cancel_evt.is_set():
                    return total_new, total_ok
                ok = self.drive.upload_file(f["path"], drive_id, cancel_evt=cancel_evt)
                self._record(history, f["name"], nome_perfil, "OK" if ok else "ERROR")
                if ok:
                    total_ok += 1
                    drive_names.add(f["name"])

        # ── Subpastas (só se recursivo=True) ─────────────────────────────────
        if recursivo:
            for name in entries:
                if cancel_evt and cancel_evt.is_set():
                    return total_new, total_ok
                sub_local = os.path.join(local_dir, name)
                if not os.path.isdir(sub_local):
                    continue
                # Cria/obtém pasta correspondente no Drive
                sub_drive_id = self._ensure_folder(name, drive_id)
                if not sub_drive_id:
                    continue
                sub_rel = f"{rel_path}/{name}" if rel_path else name
                n, o = self._espelho_dir(
                    local_dir   = sub_local,
                    drive_id    = sub_drive_id,
                    extensoes   = extensoes,
                    all_ext     = all_ext,
                    recursivo   = recursivo,
                    history     = history,
                    nome_perfil = nome_perfil,
                    rel_path    = sub_rel,
                    cancel_evt  = cancel_evt,
                    drive_cache = drive_cache,
                )
                total_new += n
                total_ok  += o

        return total_new, total_ok

    # ═══════════════════════════════════════════════════════════════════════════
    #  Helpers compartilhados
    # ═══════════════════════════════════════════════════════════════════════════
    def _ensure_folder(self, name: str, parent_id) -> str | None:
        fid = self.drive.get_or_create_folder(name, parent_id)
        if not fid:
            self.log(f"Não foi possível acessar/criar pasta '{name}' no Drive.", "ERROR")
        return fid

    def _scan_local(self, folder: str, extensions: list,
                    all_ext: bool = False) -> list[dict]:
        result = []
        try:
            for fname in os.listdir(folder):
                fpath = os.path.join(folder, fname)
                if not os.path.isfile(fpath):
                    continue
                if not all_ext:
                    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
                    if ext not in extensions:
                        continue
                result.append({
                    "name":     fname,
                    "path":     fpath,
                    "sort_key": self._extract_sort_key(fname),
                    "size":     os.path.getsize(fpath),
                })
        except Exception as e:
            self.log(f"Erro ao escanear pasta local: {e}", "ERROR")
        return result

    def _validate_count(self, sorted_files: list, qtd: int):
        count = len(sorted_files)
        if count >= qtd:
            self.log(f"Contagem OK: {count} backup(s) disponível(is).", "OK")
            return
        if count == 0:
            return
        oldest_date = self._extract_date(sorted_files[0]["name"])
        today = date.today()
        if oldest_date is None:
            try:
                import os as _os
                mtime = _os.path.getmtime(sorted_files[0]["path"])
                oldest_date = datetime.fromtimestamp(mtime).date()
            except Exception:
                oldest_date = today
        days = (today - oldest_date).days
        if days >= qtd - 1:
            self.log(
                f"ERRO: Apenas {count} de {qtd} backup(s) encontrados. "
                f"Primeiro backup tem {days} dia(s) — verifique o sistema.",
                "ERROR"
            )
        else:
            self.log(
                f"Acumulando: {count} de {qtd} "
                f"(dia {days + 1} de {qtd} — período inicial).",
                "INFO"
            )

    @staticmethod
    def _extract_sort_key(fname: str) -> str:
        m = re.search(r"(\d{8})[_\s-]?(\d{4})", fname)
        if m:
            return f"{m.group(1)}{m.group(2)}"
        m = re.search(r"(\d{8})", fname)
        if m:
            return m.group(1)
        return fname

    @staticmethod
    def _extract_date(fname: str) -> date | None:
        m = re.search(r"(\d{4})(\d{2})(\d{2})", fname)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass
        return None

    @staticmethod
    def _record(history: list, filename: str, perfil: str, status: str):
        history.append({
            "filename": filename,
            "perfil":   perfil,
            "datetime": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "status":   status,
        })
        if len(history) > 200:
            del history[:-200]
