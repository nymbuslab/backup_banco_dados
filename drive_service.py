import os
import pickle
import time
from typing import Callable

from app_paths import app_path

SCOPES     = ["https://www.googleapis.com/auth/drive"]
TOKEN_FILE = "token.pkl"
CREDS_FILE = "credentials.json"

# Retry config
MAX_RETRIES   = 3
RETRY_DELAYS  = [5, 15, 30]   # segundos entre tentativas


def _fmt_size(b: int) -> str:
    """Formata bytes para exibição legível."""
    if b < 1024:
        return f"{b} B"
    elif b < 1024 ** 2:
        return f"{b/1024:.1f} KB"
    else:
        return f"{b/1024**2:.1f} MB"


class DriveService:
    def __init__(self, log_fn: Callable = print):
        self.log     = log_fn
        self.creds   = None
        self.service = None
        self._try_load_token()

    # ── Auth ──────────────────────────────────────────────────────────────────
    def _try_load_token(self):
        token_path = app_path(TOKEN_FILE)
        if os.path.exists(token_path):
            try:
                with open(token_path, "rb") as f:
                    self.creds = pickle.load(f)
                self._build_service()
            except Exception:
                self.creds = None

    def authenticate(self) -> bool:
        creds_path = app_path(CREDS_FILE)
        if not os.path.exists(creds_path):
            self.log(f"Arquivo '{CREDS_FILE}' não encontrado em: {creds_path}", "ERROR")
            return False
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request

            if self.creds and self.creds.valid:
                return True
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
                self.creds = flow.run_local_server(port=0)

            with open(app_path(TOKEN_FILE), "wb") as f:
                pickle.dump(self.creds, f)
            self._build_service()
            return True
        except Exception as e:
            self.log(f"Erro na autenticação: {e}", "ERROR")
            return False

    def _build_service(self):
        try:
            from googleapiclient.discovery import build
            self.service = build("drive", "v3", credentials=self.creds)
        except Exception as e:
            self.log(f"Erro ao criar serviço Drive: {e}", "ERROR")
            self.service = None

    def is_authenticated(self) -> bool:
        try:
            if self.creds and self.creds.valid and self.service:
                return True
            if self.creds and self.creds.expired and self.creds.refresh_token:
                from google.auth.transport.requests import Request
                self.creds.refresh(Request())
                self._build_service()
                return True
        except Exception:
            pass
        return False

    # ── Folder helpers ────────────────────────────────────────────────────────
    def get_or_create_folder(self, name: str, parent_id: str | None = None) -> str | None:
        try:
            q = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            if parent_id:
                q += f" and '{parent_id}' in parents"
            res   = self.service.files().list(q=q, fields="files(id, name)").execute()
            files = res.get("files", [])
            if files:
                return files[0]["id"]
            meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
            if parent_id:
                meta["parents"] = [parent_id]
            folder = self.service.files().create(body=meta, fields="id").execute()
            return folder["id"]
        except Exception as e:
            self.log(f"Erro ao acessar/criar pasta '{name}': {e}", "ERROR")
            return None

    # ── File operations ───────────────────────────────────────────────────────
    def list_files_in_folder(self, folder_id: str) -> list[dict]:
        try:
            q = (f"'{folder_id}' in parents and trashed=false "
                 f"and mimeType!='application/vnd.google-apps.folder'")
            files = []
            page_token = None
            while True:
                res = self.service.files().list(
                    q=q,
                    fields="nextPageToken, files(id, name, createdTime, size)",
                    orderBy="createdTime desc",
                    pageSize=1000,
                    pageToken=page_token,
                ).execute()
                files.extend(res.get("files", []))
                page_token = res.get("nextPageToken")
                if not page_token:
                    break
            return files
        except Exception as e:
            self.log(f"Erro ao listar arquivos: {e}", "ERROR")
            return []

    def upload_file(self, local_path: str, folder_id: str, cancel_evt=None) -> bool:
        """
        Upload com:
        - Progresso em tempo real (KB enviados / tamanho total)
        - Taxa de transferência (KB/s)
        - Retry automático em caso de falha de rede (até MAX_RETRIES tentativas)
        """
        from googleapiclient.http import MediaFileUpload
        import googleapiclient.errors

        fname     = os.path.basename(local_path)
        file_size = os.path.getsize(local_path)
        size_str  = _fmt_size(file_size)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if cancel_evt and cancel_evt.is_set():
                    self.log(f"Upload cancelado: {fname}", "WARN")
                    return False
                media = MediaFileUpload(local_path, resumable=True, chunksize=256 * 1024)
                meta  = {"name": fname, "parents": [folder_id]}
                req   = self.service.files().create(body=meta, media_body=media, fields="id")

                response     = None
                sent_bytes   = 0
                last_bytes   = 0
                t_start      = time.time()
                t_chunk      = time.time()
                t_last_log   = 0.0
                last_pct     = -1

                while response is None:
                    if cancel_evt and cancel_evt.is_set():
                        self.log(f"Upload cancelado: {fname}", "WARN")
                        return False
                    status, response = req.next_chunk()

                    if status:
                        sent_bytes    = status.resumable_progress
                        elapsed_chunk = max(time.time() - t_chunk, 0.01)
                        elapsed_total = max(time.time() - t_start, 0.01)

                        # Taxa instantânea (última janela) e média
                        delta     = max(sent_bytes - last_bytes, 0)
                        speed     = delta / elapsed_chunk
                        pct       = int(status.progress() * 100)

                        now = time.time()
                        if (now - t_last_log) >= 0.8 or pct != last_pct:
                            self.log(
                                f"{fname}  "
                                f"[{_fmt_size(sent_bytes)} / {size_str}]  "
                                f"{pct}%  "
                                f"@ {_fmt_size(int(speed))}/s",
                                "PROGRESS"
                            )
                            t_last_log = now
                            last_pct   = pct
                        last_bytes = sent_bytes
                        t_chunk = time.time()

                self.log(
                    f"Upload concluído: {fname}  "
                    f"[{size_str}]  "
                    f"em {time.time() - t_start:.1f}s",
                    "OK"
                )
                return True

            except Exception as e:
                is_network = any(k in str(type(e).__name__).lower()
                                 for k in ("timeout", "connection", "transport", "socket"))
                is_http    = "HttpError" in type(e).__name__

                if cancel_evt and cancel_evt.is_set():
                    self.log(f"Upload cancelado: {fname}", "WARN")
                    return False

                if attempt < MAX_RETRIES:
                    delay = RETRY_DELAYS[attempt - 1]
                    self.log(
                        f"Tentativa {attempt}/{MAX_RETRIES} falhou: {e}. "
                        f"Reenvio em {delay}s...",
                        "WARN"
                    )
                    time.sleep(delay)
                    # Reconstrói o serviço em caso de erro de conexão
                    if is_network:
                        self._build_service()
                else:
                    self.log(
                        f"Upload falhou após {MAX_RETRIES} tentativas: {fname} — {e}",
                        "ERROR"
                    )
                    return False

        return False

    def delete_file(self, file_id: str, file_name: str) -> bool:
        try:
            self.service.files().delete(fileId=file_id).execute()
            self.log(f"Arquivo removido do Drive: {file_name}", "INFO")
            return True
        except Exception as e:
            self.log(f"Erro ao deletar '{file_name}': {e}", "ERROR")
            return False

    def disconnect(self):
        self.creds   = None
        self.service = None
        token_path   = app_path(TOKEN_FILE)
        if os.path.exists(token_path):
            os.remove(token_path)
