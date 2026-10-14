@echo off
setlocal EnableDelayedExpansion
title SiteCapture - Build

echo.
echo  ============================================
echo   SiteCapture  --  Build Script
echo  ============================================
echo.

:: Activate venv
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo  WARNING: venv not found - run setup.bat first or using system Python
    echo.
)

:: Generate icon
echo  [1/3]  Generating icon...
python make_icon.py
if %ERRORLEVEL% NEQ 0 (
    echo         WARNING: Icon generation failed - build will continue without icon
)

:: Install / update PyInstaller
echo  [2/3]  Installing PyInstaller...
pip install pyinstaller --quiet --upgrade
if %ERRORLEVEL% NEQ 0 (
    echo  ERROR: Could not install PyInstaller
    pause & exit /b 1
)

:: Build with PyInstaller
echo  [3/3]  Building executable...
echo.
pyinstaller --noconfirm --onedir --windowed ^
  --name "SiteCapture" ^
  --icon "icon.ico" ^
  --add-data "icon.ico;." ^
  --collect-all customtkinter ^
  --hidden-import yt_dlp ^
  --hidden-import browser_cookie3 ^
  --hidden-import anthropic ^
  --hidden-import lxml ^
  --hidden-import bs4 ^
  --hidden-import PIL ^
  main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  ERROR: PyInstaller build failed. See output above for details.
    pause & exit /b 1
)

echo.
echo  Build complete!
echo  Portable app: dist\SiteCapture\SiteCapture.exe
echo.

:: Try to build installer with Inno Setup
set "INNO=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "%INNO%" set "INNO=C:\Program Files\Inno Setup 6\ISCC.exe"

if exist "%INNO%" (
    echo  Building installer...
    "%INNO%" installer.iss
    if !ERRORLEVEL! EQU 0 (
        echo  Installer created: installer_output\SiteCapture_Setup_v1.0.0.exe
    ) else (
        echo  WARNING: Inno Setup build failed - portable app still available
    )
) else (
    echo  ─────────────────────────────────────────────────
    echo  To also create an installer .exe, install Inno Setup 6:
    echo    https://jrsoftware.org/isdl.php
    echo  Then re-run this script.
    echo  ─────────────────────────────────────────────────
)

echo.
pause
