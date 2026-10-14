@echo off
setlocal EnableDelayedExpansion
title SiteCapture - Setup
color 0B

echo.
echo  ============================================
echo    SiteCapture  -  First-time Setup
echo  ============================================
echo.

:: ── Check Python ─────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found.
    echo.
    echo  Please install Python 3.10 or newer from:
    echo    https://www.python.org/downloads/
    echo.
    echo  During installation, check "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo  Found: %PY_VER%
echo.

:: ── Create virtual environment ───────────────────────────────────────────────
if exist "venv\Scripts\activate.bat" (
    echo  [OK] Virtual environment already exists.
) else (
    echo  Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo  [ERROR] Could not create virtual environment.
        pause
        exit /b 1
    )
    echo  [OK] Virtual environment created.
)

:: ── Install dependencies ──────────────────────────────────────────────────────
echo.
echo  Installing dependencies (this may take 1-2 minutes)...
echo  --------------------------------------------------------
call venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  [ERROR] Some packages failed to install.
    echo  Check your internet connection and try again.
    pause
    exit /b 1
)
echo  [OK] All dependencies installed.

:: ── Generate icon ──────────────────────────────────────────────────────────────
echo.
echo  Generating application icon...
python make_icon.py
if errorlevel 1 (
    echo  [WARN] Icon generation failed (Pillow may be missing). Continuing without icon.
) else (
    echo  [OK] Icon generated.
)

:: ── Desktop shortcut ──────────────────────────────────────────────────────────
echo.
echo  Creating desktop shortcut...
set "HERE=%~dp0"
set "HERE=%HERE:~0,-1%"

powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; ^
   $lnk = $ws.CreateShortcut([IO.Path]::Combine([Environment]::GetFolderPath('Desktop'), 'SiteCapture.lnk')); ^
   $lnk.TargetPath = '%HERE%\run.bat'; ^
   $lnk.WorkingDirectory = '%HERE%'; ^
   $lnk.Description = 'SiteCapture - Download websites with media'; ^
   $lnk.WindowStyle = 1; ^
   $lnk.IconLocation = '%HERE%\icon.ico'; ^
   $lnk.Save()"

if errorlevel 1 (
    echo  [WARN] Could not create desktop shortcut (run run.bat manually).
) else (
    echo  [OK] Desktop shortcut created.
)

:: ── Done ──────────────────────────────────────────────────────────────────────
echo.
echo  ============================================
echo    Setup complete!
echo.
echo    Launch options:
echo      1. Desktop shortcut "SiteCapture"
echo      2. Double-click run.bat in this folder
echo  ============================================
echo.
set /p "LAUNCH=Launch the app now? (Y/N): "
if /i "!LAUNCH!"=="Y" (
    start "" "%HERE%\run.bat"
)
endlocal
