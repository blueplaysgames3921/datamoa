@echo off
REM DataMoA Python backend starter for Windows
REM Run from project root: start_backend.bat

SET SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo Starting DataMoA backend...
python --version

REM Check if fastapi is installed
python -c "import fastapi" 2>nul
IF %ERRORLEVEL% NEQ 0 (
    echo Installing Python dependencies...
    pip install -r requirements.txt
)

SET PYTHONPATH=%SCRIPT_DIR%
python core\main.py --port %DATAMOA_PORT%
IF "%DATAMOA_PORT%"=="" SET DATAMOA_PORT=7532
python core\main.py --port %DATAMOA_PORT%
