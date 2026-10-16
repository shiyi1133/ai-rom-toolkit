@echo off
setlocal
call "%~dp0env.cmd"
cd /d "%~dp0"
"%ROMKIT_PYTHON%" -X utf8 tools\self_test.py
set "RC=%errorlevel%"
echo.
echo Self-test exit code: %RC%
pause
exit /b %RC%
