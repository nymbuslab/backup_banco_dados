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
import socket
import tempfile
import threading
import uuid
from copy import deepcopy
from datetime import datetime

import keyring

from app_paths import app_path

CONFIG_FILE = "backup_config.json"
KEYRING_SERVICE = "GR7BackupManager"
KEYRING_SMTP_PASSWORD = "smtp_password"


def _new_id() -> str:
    return "prof_" + uuid.uuid4().hex[:8]


class ConfigManager:
    def __init__(self):
        self.path = app_path(CONFIG_FILE)
        self.bak_path = self.path + ".bak"
        self._lock = threading.RLock()
        self._cache = None

    # ── Persistence ─────────────────────────────────────────────────────────────
    def save(self, data: dict):
        with self._lock:
            self._save_unlocked(data)

    def load(self) -> dict:
        with self._lock:
            return self._load_unlocked()

    def update(self, updater):
        with self._lock:
            data = self._load_unlocked()
            result = updater(data)
            self._save_unlocked(data)
            return data if result is None else result

    def _save_unlocked(self, data: dict):
        dir_path = os.path.dirname(self.path) or "."
        tmp_path = None
        try:
            data_to_save = self._normalize_data(data)
            fd, tmp_path = tempfile.mkstemp(prefix="backup_config.", suffix=".tmp", dir=dir_path)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, indent=2, ensure_ascii=False)
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
            self._cache = self._migrate(data_to_save)
        except Exception as e:
            if tmp_path:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            print(f"[ConfigManager] Erro ao salvar: {e}")

    def _load_unlocked(self) -> dict:
        if self._cache is not None:
            return deepcopy(self._cache)
        if not os.path.exists(self.path):
            self._cache = self._empty()
            return deepcopy(self._cache)
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self._cache = self._migrate(raw)
            return deepcopy(self._cache)
        except Exception:
            bak = self._try_load_backup()
            if bak is not None:
                self._cache = self._migrate(bak)
                return deepcopy(self._cache)
            self._quarantine_broken_file()
            self._cache = self._empty()
            return deepcopy(self._cache)

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

    # ── Profile helpers ─────────────────────────────────────────────────────────
    def get_profiles(self) -> list:
        return self.load().get("profiles", [])

    def save_profile(self, profile: dict):
        """Insere ou atualiza um perfil pelo id."""

        def _update(data: dict):
            profiles = data.get("profiles", [])
            idx = next((i for i, p in enumerate(profiles) if p["id"] == profile["id"]), None)
            if idx is not None:
                profiles[idx] = profile
            else:
                profiles.append(profile)
            data["profiles"] = profiles

        self.update(_update)

    def delete_profile(self, profile_id: str):
        self.update(lambda data: data.__setitem__(
            "profiles",
            [p for p in data.get("profiles", []) if p["id"] != profile_id],
        ))

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

    # ── Internal ────────────────────────────────────────────────────────────────
    @staticmethod
    def _empty() -> dict:
        data = {
            "profiles":      [],
            "sync_active":   False,
            "auto_sync":     False,
            "sync_interval": "1 hora",
            "history":       [],
            "installation_id": "inst_" + uuid.uuid4().hex[:10],
            "installation_label": "",
            "admin_alerts_enabled": False,
            "alert_state": {},
            "email_config": {
                "smtp_host":     "",
                "smtp_port":     587,
                "smtp_user":     "",
                "smtp_password": "",
                "to_addr":       "",
                "use_tls":       True,
            },
        }
        ConfigManager._inject_secret(data["email_config"])
        return data

    @staticmethod
    def _migrate(raw: dict) -> dict:
        """
        Converte formato antigo (campos soltos) para o novo (profiles[]).
        Roda apenas uma vez; depois o campo "profiles" já existe.
        """
        defaults = ConfigManager._empty()
        if "profiles" in raw:
            defaults.update(raw)
            defaults["installation_id"] = str(defaults.get("installation_id") or ("inst_" + uuid.uuid4().hex[:10]))
            defaults["installation_label"] = ConfigManager._normalize_installation_label(
                defaults.get("installation_label"),
                defaults.get("profiles", []),
            )
            defaults["admin_alerts_enabled"] = bool(defaults.get("admin_alerts_enabled", False))
            defaults["alert_state"] = ConfigManager._normalize_alert_state(defaults.get("alert_state"))
            defaults["email_config"] = ConfigManager._normalize_email_config(defaults.get("email_config"))
            ConfigManager._migrate_plaintext_password(defaults["email_config"])
            ConfigManager._inject_secret(defaults["email_config"])
            return defaults

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
        defaults["installation_label"] = ConfigManager._normalize_installation_label(
            raw.get("installation_label"),
            defaults.get("profiles", []),
        )
        defaults["admin_alerts_enabled"] = bool(raw.get("admin_alerts_enabled", False))
        defaults["alert_state"] = ConfigManager._normalize_alert_state(raw.get("alert_state"))
        defaults["email_config"] = ConfigManager._normalize_email_config(defaults.get("email_config"))
        ConfigManager._migrate_plaintext_password(defaults["email_config"])
        ConfigManager._inject_secret(defaults["email_config"])
        return defaults

    @staticmethod
    def _normalize_email_config(email_cfg) -> dict:
        defaults_email = {
            "smtp_host": "",
            "smtp_port": 587,
            "smtp_user": "",
            "smtp_password": "",
            "to_addr": "",
            "use_tls": True,
        }
        if not isinstance(email_cfg, dict):
            return dict(defaults_email)
        data = dict(defaults_email)
        data.update(email_cfg)
        return data

    @staticmethod
    def _normalize_data(data: dict) -> dict:
        normalized = dict(data)
        normalized["installation_id"] = str(normalized.get("installation_id") or ("inst_" + uuid.uuid4().hex[:10]))
        normalized["installation_label"] = ConfigManager._normalize_installation_label(
            normalized.get("installation_label"),
            normalized.get("profiles", []),
        )
        normalized["admin_alerts_enabled"] = bool(normalized.get("admin_alerts_enabled", False))
        normalized["alert_state"] = ConfigManager._normalize_alert_state(normalized.get("alert_state"))
        email_cfg = ConfigManager._normalize_email_config(normalized.get("email_config"))
        password = email_cfg.get("smtp_password", "")
        if password:
            ConfigManager._set_smtp_password(password)
        email_cfg["smtp_password"] = ""
        normalized["email_config"] = email_cfg
        return normalized

    @staticmethod
    def _normalize_installation_label(label, profiles: list) -> str:
        text = str(label or "").strip()
        if text:
            return text
        clientes = []
        for profile in profiles or []:
            cliente = str(profile.get("cliente", "")).strip()
            if cliente and cliente not in clientes:
                clientes.append(cliente)
        if len(clientes) == 1:
            return clientes[0]
        try:
            return socket.gethostname().strip()
        except Exception:
            return ""

    @staticmethod
    def _normalize_alert_state(alert_state) -> dict:
        if not isinstance(alert_state, dict):
            return {}
        normalized = {}
        for key, value in alert_state.items():
            if not isinstance(key, str):
                continue
            if isinstance(value, dict):
                normalized[key] = {
                    "last_sent_at": str(value.get("last_sent_at", "") or ""),
                    "last_message": str(value.get("last_message", "") or ""),
                }
        return normalized

    @staticmethod
    def _migrate_plaintext_password(email_cfg: dict):
        plaintext = email_cfg.get("smtp_password", "")
        if plaintext:
            ConfigManager._set_smtp_password(plaintext)
            email_cfg["smtp_password"] = ""

    @staticmethod
    def _inject_secret(email_cfg: dict):
        email_cfg["smtp_password"] = ConfigManager._get_smtp_password()

    @staticmethod
    def _get_smtp_password() -> str:
        try:
            return keyring.get_password(KEYRING_SERVICE, KEYRING_SMTP_PASSWORD) or ""
        except Exception:
            return ""

    @staticmethod
    def _set_smtp_password(password: str):
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_SMTP_PASSWORD, password)
        except Exception as e:
            print(f"[ConfigManager] Erro ao salvar senha no keyring: {e}")
