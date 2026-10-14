@echo off
cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo Setup has not been run yet. Running setup...
    call setup.bat
    exit /b
)

call venv\Scripts\activate.bat
if not exist "icon.ico" python make_icon.py
python main.py
