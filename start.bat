@echo off
REM ── Job Finder: one-click launcher for Windows ──────────────────────────
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 ( set PY=py ) else ( set PY=python )

echo.
echo  Setting up Job Finder...
if not exist ".venv\" (
    echo  Creating virtual environment ^(first run only^)...
    %PY% -m venv .venv
)
call ".venv\Scripts\activate.bat"

echo  Installing dependencies ^(first run may take a minute^)...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

echo  Launching app...
python run.py --open
pause
