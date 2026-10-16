@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Initialize_Environment.ps1" %*
set "RC=%errorlevel%"
echo.
echo Initialization exit code: %RC%
pause
exit /b %RC%
