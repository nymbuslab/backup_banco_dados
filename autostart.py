"""
AutoStart
─────────
Gerencia a entrada de inicialização automática no Windows via registro.
Chave: HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run

Não requer privilégios de administrador (HKCU).
"""

import sys
import os

APP_NAME = "GR7BackupManager"


def _get_startup_cmd() -> str:
    """
    Retorna o comando registrado no Windows para iniciar o app.

    IMPORTANTE:
    - O caminho DEVE estar entre aspas duplas (caso haja espaços no path)
    - A flag --minimized faz o app iniciar direto na bandeja, sem abrir janela
    """
    if getattr(sys, "frozen", False):
        # Rodando como .exe (PyInstaller) — sys.executable aponta para o .exe correto
        exe = sys.executable
    else:
        # Desenvolvimento: usa pythonw para não abrir janela de console
        exe = os.path.abspath(sys.argv[0])
        exe = f'pythonw "{exe}"'
        return f'{exe} --minimized'

    # Sempre envolve o caminho em aspas — protege contra espaços no path
    return f'"{exe}" --minimized'


def is_enabled() -> bool:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ
        )
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def enable() -> bool:
    try:
        import winreg
        cmd = _get_startup_cmd()
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"[AutoStart] Erro ao ativar: {e}")
        return False


def disable() -> bool:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"[AutoStart] Erro ao desativar: {e}")
        return False


def get_registered_cmd() -> str:
    """Retorna o comando atualmente registrado no Windows (para debug)."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ
        )
        value, _ = winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return value
    except Exception:
        return "(não registrado)"
