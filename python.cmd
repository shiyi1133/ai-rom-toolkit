@echo off
if not exist "%~dp0runtime\python\python.exe" (
  echo Run Initialize_Environment.cmd first.
  exit /b 1
)
"%~dp0runtime\python\python.exe" -X utf8 %*
exit /b %errorlevel%
