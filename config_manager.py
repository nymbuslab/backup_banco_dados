"""
ConfigManager v2
────────────────
Formato do backup_config.json:

{
  "profiles": [
    {
      "id": "prof_abc123",
      "nome": "Banco TESTE",
      "modo": "rotacao",          // "rotacao" | "espelho"
      "folder_pai": "GR7 BACKUP MANAGER",
      "cliente": "TESTE",
      "backup_dir": "D:/GR7/Backup",
      "extensoes": ".sql",
      "qtd_backups": 3,           // só rotação
      "ativo": true
    },
    ...
  ],
  "sync_active":    false,
  "auto_sync":      false,
  "sync_interval":  "1 hora",
  "history":        [ ... ]
}

Migração automática: se encontrar o formato antigo (sem "profiles"),
converte para o novo formato preservando todos os dados.
"""

import json
import os
import uuid
from datetime import datetime
import tempfile

from app_paths import app_path

CONFIG_FILE = "backup_config.json"


def _new_id() -> str:
    return "prof_" + uuid.uuid4().hex[:8]


class ConfigManager:
    def __init__(self):
        self.path = app_path(CONFIG_FILE)
        self.bak_path = self.path + ".bak"

    # ── Persistence ───────────────────────────────────────────────────────────
    def save(self, data: dict):
        dir_path = os.path.dirname(self.path) or "."
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(prefix="backup_config.", suffix=".tmp", dir=dir_path)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            if os.path.exists(self.path):
                try:
                    with open(self.path, "r", encoding="utf-8") as src:
                        prev = src.read()
                    with open(self.bak_path, "w", encoding="utf-8") as dst:
                        dst.write(prev)
                        dst.flush()
                        os.fsync(dst.fileno())
                except Exception:
                    pass
            os.replace(tmp_path, self.path)
        except Exception as e:
            if tmp_path:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            print(f"[ConfigManager] Erro ao salvar: {e}")

    def load(self) -> dict:
        if not os.path.exists(self.path):
            return self._empty()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            return self._migrate(raw)
        except Exception:
            bak = self._try_load_backup()
            if bak is not None:
                return self._migrate(bak)
            self._quarantine_broken_file()
            return self._empty()

    def _try_load_backup(self) -> dict | None:
        if not os.path.exists(self.bak_path):
            return None
        try:
            with open(self.bak_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _quarantine_broken_file(self):
        try:
            if not os.path.exists(self.path):
                return
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            bad_path = self.path + f".corrupt-{stamp}"
            os.replace(self.path, bad_path)
        except Exception:
            pass

    # ── Profile helpers ───────────────────────────────────────────────────────
    def get_profiles(self) -> list:
        return self.load().get("profiles", [])

    def save_profile(self, profile: dict):
        """Insere ou atualiza um perfil pelo id."""
        data = self.load()
        profiles = data.get("profiles", [])
        idx = next((i for i, p in enumerate(profiles) if p["id"] == profile["id"]), None)
        if idx is not None:
            profiles[idx] = profile
        else:
            profiles.append(profile)
        data["profiles"] = profiles
        self.save(data)

    def delete_profile(self, profile_id: str):
        data = self.load()
        data["profiles"] = [p for p in data.get("profiles", []) if p["id"] != profile_id]
        self.save(data)

    def new_profile(self, folder_pai: str = "GR7 BACKUP MANAGER") -> dict:
        """Retorna um perfil vazio com valores padrão."""
        return {
            "id":           _new_id(),
            "nome":         "",
            "modo":         "rotacao",
            "folder_pai":   folder_pai,
            "cliente":      "",
            "backup_dir":   "",
            "extensoes":    ".sql",
            "qtd_backups":  3,
            "ativo":        True,
            "email_alerta": False,
        }

    # ── Internal ──────────────────────────────────────────────────────────────
    @staticmethod
    def _empty() -> dict:
        return {
            "profiles":      [],
            "sync_active":   False,
            "auto_sync":     False,
            "sync_interval": "1 hora",
            "history":       [],
            "email_config": {
                "smtp_host":     "",
                "smtp_port":     587,
                "smtp_user":     "",
                "smtp_password": "",
                "to_addr":       "",
                "use_tls":       True,
            },
        }

    @staticmethod
    def _migrate(raw: dict) -> dict:
        """
        Converte formato antigo (campos soltos) para o novo (profiles[]).
        Roda apenas uma vez — depois o campo "profiles" já existe.
        """
        defaults = ConfigManager._empty()
        if "profiles" in raw:
            defaults.update(raw)
            return defaults

        # Formato antigo detectado → converte
        profile = {
            "id":          _new_id(),
            "nome":        raw.get("cliente", "Perfil Migrado"),
            "modo":        "rotacao",
            "folder_pai":  raw.get("folder_pai", "GR7 BACKUP MANAGER"),
            "cliente":     raw.get("cliente", ""),
            "backup_dir":  raw.get("backup_dir", ""),
            "extensoes":   raw.get("extensoes", ".sql"),
            "qtd_backups": int(raw.get("qtd_backups", 3)),
            "ativo":       True,
        }

        defaults.update({
            "profiles":      [profile],
            "sync_active":   raw.get("sync_active", False),
            "auto_sync":     raw.get("auto_sync", False),
            "sync_interval": raw.get("sync_interval", "1 hora"),
            "history":       raw.get("history", []),
        })
        return defaults
