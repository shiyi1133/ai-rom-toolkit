@echo off
setlocal
call "%~dp0env.cmd"
cd /d "%~dp0"
"%ROMKIT_PYTHON%" -X utf8 tools\check_environment.py
set "RC=%errorlevel%"
echo.
echo Environment check exit code: %RC%
pause
exit /b %RC%
