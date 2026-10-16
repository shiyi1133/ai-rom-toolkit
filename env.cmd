@echo off
set "ROMKIT_ROOT=%~dp0"
set "ROMKIT_PYTHON=%~dp0runtime\python\python.exe"
set "PATH=%~dp0;%~dp0runtime\python;%~dp0runtime\arm\bin;%~dp0runtime\rgbds;%~dp0runtime\mgba;%PATH%"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
exit /b 0
