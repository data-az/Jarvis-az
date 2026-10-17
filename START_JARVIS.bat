@echo off
setlocal
title Jarvis AZ
cd /d "%~dp0program"
if errorlevel 1 (
  echo The "program" folder was not found next to this file.
  echo Do not move START_JARVIS.bat out of the Jarvis folder.
  pause
  exit /b 1
)

rem --- look for Python 3 (3.11 is the best choice)
set "PYCMD="
for %%V in (3.11 3.12 3.10 3.9) do (
  if not defined PYCMD (
    py -%%V -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYCMD=py -%%V"
  )
)
if not defined PYCMD (
  python -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PYCMD=python"
)
if not defined PYCMD (
  py -3 -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PYCMD=py -3"
)
if not defined PYCMD goto :nopython

%PYCMD% launcher.py
set "RC=%errorlevel%"
if not "%RC%"=="0" (
  echo.
  pause
)
exit /b %RC%

:nopython
echo.
echo  Python was not found on this computer.
echo.
echo  1. A download page opens now. Download "Windows installer 64-bit" for Python 3.11.
echo  2. In the installer TICK "Add python.exe to PATH" at the bottom of the first window.
echo  3. Press Install, then run START_JARVIS.bat again.
echo.
echo  Windows 8.1: Python 3.11 is the newest version that works there.
echo.
start "" "https://www.python.org/downloads/release/python-3119/"
pause
exit /b 1
