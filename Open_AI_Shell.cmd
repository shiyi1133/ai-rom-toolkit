@echo off
setlocal
call "%~dp0env.cmd"
cd /d "%~dp0"
echo ROM Toolkit: Windows native, local PATH only.
echo Read 00_README_CN.txt and prompts\01_INITIALIZE.txt first.
%COMSPEC% /K
endlocal
