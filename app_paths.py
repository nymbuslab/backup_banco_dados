"""
app_paths.py
─────────────
Resolve caminhos de arquivos corretamente tanto em modo desenvolvimento (.py)
quanto empacotado pelo PyInstaller (.exe).

Problema:
  Quando rodando como .exe, __file__ aponta para uma pasta temporária de
  extração (_MEIXXXXXX), não para a pasta onde o .exe está instalado.
  sys.executable aponta para o .exe correto.

Solução:
  - Modo .exe  → base = pasta do GDriveBackup.exe  (sys.executable)
  - Modo .py   → base = pasta do script main.py     (sys.argv[0])
"""

import os
import sys


def app_dir() -> str:
    """Retorna a pasta onde o executável (ou script principal) está localizado."""
    if getattr(sys, "frozen", False):
        # PyInstaller .exe
        return os.path.dirname(sys.executable)
    else:
        # Script .py em desenvolvimento
        return os.path.dirname(os.path.abspath(sys.argv[0]))


def app_path(filename: str) -> str:
    """Retorna o caminho absoluto de um arquivo na pasta do app."""
    return os.path.join(app_dir(), filename)
