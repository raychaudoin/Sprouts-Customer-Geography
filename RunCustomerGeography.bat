@echo off
setlocal
cd /d "%~dp0"
python scripts\app01\serve_dashboard.py --open
set "APP01_EXIT=%ERRORLEVEL%"
if not "%APP01_EXIT%"=="0" (
  echo.
  echo APP-01 stopped before launch. Review the message above, correct the local input or port issue, and run this launcher again.
  pause
)
exit /b %APP01_EXIT%
