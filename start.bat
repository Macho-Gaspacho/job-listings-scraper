@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHON="

where py >nul 2>&1
if errorlevel 1 goto try_python

py -3.12 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 set "PYTHON=py -3.12"
if defined PYTHON goto found

py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 set "PYTHON=py -3"
if defined PYTHON goto found

:try_python
where python >nul 2>&1
if errorlevel 1 goto missing
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 set "PYTHON=python"
if defined PYTHON goto found

:missing
echo Python 3.10 or newer was not found.
echo Install Python 3.12 from https://www.python.org/downloads/
echo On the first screen, turn on "Add python.exe to PATH".
echo.
pause
exit /b 1

:found
if exist ".venv\Scripts\python.exe" goto install
echo Creating a private Python folder (.venv)...
%PYTHON% -m venv .venv
if errorlevel 1 goto venv_failed

:install
echo Installing the tools this program needs. The first time can take a few minutes...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto pip_failed

echo.
".venv\Scripts\python.exe" scrape.py
set "STATUS=%errorlevel%"
echo.
if "%STATUS%"=="0" echo Done. Open output\jobs.xlsx to see the jobs.
if not "%STATUS%"=="0" echo The search stopped. Read the messages above.
pause
exit /b %STATUS%

:venv_failed
echo Could not create .venv.
pause
exit /b 1

:pip_failed
echo Could not install the tools. Check your internet connection and try again.
pause
exit /b 1
