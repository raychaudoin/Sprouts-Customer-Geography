@echo off
setlocal
cd /d "%~dp0"
python scripts\arch01\serve_spike.py
endlocal
