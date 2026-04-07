@echo off
setlocal enableextensions
pushd "%~dp0"
echo ============================================
echo  GR7 Backup Manager - Build EXE
echo ============================================
echo.

set "MODE=%~1"
if "%MODE%"=="" set "MODE=win11"

if /I "%MODE%"=="win7" goto :WIN7
goto :WIN11

:WIN11
echo [1/5] Preparando ambiente para Windows 10/11 (Python atual)...
set "VENV_DIR=.venv-build"
set "PY=python"
where py >nul 2>&1
if not errorlevel 1 set "PY=py -3"
goto :SETUP

:WIN7
echo [1/5] Preparando ambiente para Windows 7 (Python 3.8)...
set "VENV_DIR=.venv-win7"
set "PY="

where py >nul 2>&1
if not errorlevel 1 (
  py -3.8 -c "import sys; raise SystemExit(0 if sys.version_info[:2]==(3,8) else 1)" >nul 2>&1
  if not errorlevel 1 set "PY=py -3.8"
)

if "%PY%"=="" (
  python -c "import sys; raise SystemExit(0 if sys.version_info[:2]==(3,8) else 1)" >nul 2>&1
  if not errorlevel 1 set "PY=python"
)

if "%PY%"=="" (
  echo ERRO: Python 3.8 nao encontrado.
  echo Instale o Python 3.8 (x64) e tente novamente.
  echo Dica: se tiver o Python Launcher, o comando deve funcionar: py -3.8
  echo.
  if "%NO_PAUSE%"=="1" exit /b 1
  pause
  exit /b 1
)
goto :SETUP

:SETUP

if not exist "%VENV_DIR%\Scripts\python.exe" (
  %PY% -m venv "%VENV_DIR%"
)
call "%VENV_DIR%\Scripts\activate.bat"
python -m pip install -U pip setuptools wheel

echo.
echo [2/5] Fechando executavel (se estiver aberto) e limpando build anterior...
taskkill /IM GR7BackupManager.exe /F >nul 2>&1
ping 127.0.0.1 -n 2 >nul
if exist "dist\GR7BackupManager.exe" del /f /q "dist\GR7BackupManager.exe" >nul 2>&1
if exist "dist" rmdir /s /q "dist" >nul 2>&1
if exist "build" rmdir /s /q "build" >nul 2>&1

echo.
echo [3/5] Instalando dependencias...
echo Incluindo dependencias do app definidas em requirements.txt ^(inclui keyring^)
python -m pip install -r requirements.txt
python -m pip install pyinstaller

echo.
echo [4/5] Gerando executavel...
pyinstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name "GR7BackupManager" ^
  --icon "assets\gr7backup.ico" ^
  --add-data "assets\gr7backup.ico;assets" ^
  --add-data "assets\gr7backup.ico;." ^
  --hidden-import=pystray._win32 ^
  --hidden-import=PIL ^
  --hidden-import=keyring.backends.Windows ^
  --hidden-import=win32ctypes.pywin32.pywintypes ^
  --hidden-import=win32ctypes.pywin32.win32cred ^
  --collect-data=customtkinter ^
  main.py

echo.
echo [5/5] Concluido!
echo Executavel gerado em: dist\GR7BackupManager.exe
echo.
echo IMPORTANTE: Coloque credentials.json na mesma pasta que GR7BackupManager.exe
echo.
popd
if "%NO_PAUSE%"=="1" exit /b 0
pause
