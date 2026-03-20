import json
import os

from app_paths import app_path

CONFIG_FILE = "backup_config.json"


class ConfigManager:
    def __init__(self):
        self.path = app_path(CONFIG_FILE)

    def save(self, data: dict):
        try:
            existing = self.load() or {}
            existing.update(data)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[ConfigManager] Erro ao salvar: {e}")

    def load(self) -> dict:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
