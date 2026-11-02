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
if exist ".venv\Scripts\python.exe" goto hash_requirements
echo Creating a private Python folder (.venv)...
%PYTHON% -m venv .venv
if errorlevel 1 goto venv_failed

REM Skip pip when .venv\.requirements.sha256 matches the sha256 of requirements.txt.
:hash_requirements
".venv\Scripts\python.exe" -c "import hashlib,pathlib,sys; h=hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest(); p=pathlib.Path('.venv/.requirements.sha256'); same=p.is_file() and p.read_text(encoding='utf-8').strip()==h; sys.exit(0 if same else 2)"
if "%errorlevel%"=="0" goto tools_ready

echo Installing the tools this program needs. The first time can take a few minutes...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto pip_failed
".venv\Scripts\python.exe" -c "import hashlib,pathlib; h=hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest(); pathlib.Path('.venv/.requirements.sha256').write_text(h + chr(10), encoding='utf-8')"
goto run_scrape

:tools_ready
echo The tools are already installed.
goto run_scrape

:run_scrape
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
if exist ".venv\.requirements.sha256" goto pip_keep
echo Could not install the tools. Check your internet connection and try again.
pause
exit /b 1

:pip_keep
echo Could not update the tools (no internet?). Continuing with the ones already installed.
goto run_scrape
