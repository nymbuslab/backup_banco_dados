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
        script = os.path.abspath(sys.argv[0])
        py_exe = sys.executable
        py_dir = os.path.dirname(py_exe)
        base = os.path.basename(py_exe).lower()
        if base == "pythonw.exe":
            pythonw = py_exe
        else:
            candidate = os.path.join(py_dir, "pythonw.exe")
            pythonw = candidate if os.path.exists(candidate) else py_exe
        return f'"{pythonw}" "{script}" --minimized'

    # Sempre envolve o caminho em aspas — protege contra espaços no path
    return f'"{exe}" --minimized'


def is_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ
        ) as key:
            winreg.QueryValueEx(key, APP_NAME)
        return True
    except (OSError, ImportError):
        return False


def enable() -> bool:
    try:
        import winreg
        cmd = _get_startup_cmd()
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
        return True
    except (OSError, ImportError) as e:
        print(f"[AutoStart] Erro ao ativar: {e}")
        return False


def disable() -> bool:
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, APP_NAME)
        return True
    except (OSError, ImportError) as e:
        print(f"[AutoStart] Erro ao desativar: {e}")
        return False


def get_registered_cmd() -> str:
    """Retorna o comando atualmente registrado no Windows (para debug)."""
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ
        ) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
        return value
    except (OSError, ImportError):
        return "(não registrado)"
