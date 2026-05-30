@echo off
setlocal
set "DATA_DIR=%APPDATA%\wm2026"
set "PYTHON_EXE=%DATA_DIR%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=py -3"
cd /d "%DATA_DIR%"
%PYTHON_EXE% "%DATA_DIR%\wm2026_server.py"
