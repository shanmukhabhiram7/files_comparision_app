@echo off
REM Create the virtual environment on first run, then start the app.
setlocal

if not exist ".venv" (
    echo Creating virtual environment...
    py -m venv .venv 2>nul || python -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt
python app.py

endlocal
