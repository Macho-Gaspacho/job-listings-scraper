#!/bin/bash
# One-command start for macOS and Linux.
# On a Mac you can double-click start.command instead.

cd "$(dirname "$0")" || exit 1

hold_window() {
  echo
  echo "Press Enter to close this window."
  read -r _
}

python_ok() {
  "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1
}

PYTHON=""
if command -v python3.12 >/dev/null 2>&1 && python_ok python3.12; then
  PYTHON="python3.12"
elif command -v python3 >/dev/null 2>&1 && python_ok python3; then
  PYTHON="python3"
fi

if [ -z "$PYTHON" ]; then
  echo "Python 3.10 or newer was not found."
  echo "Install Python 3.12 from https://www.python.org/downloads/"
  echo "On a Mac, after installing, double-click:"
  echo '    "/Applications/Python 3.12/Install Certificates.command"'
  hold_window
  exit 1
fi

echo "Using $("$PYTHON" -c 'import sys; print(sys.version.split()[0])')"

if [ ! -x .venv/bin/python ]; then
  echo "Creating a private Python folder (.venv)..."
  if ! "$PYTHON" -m venv .venv; then
    echo "Could not create .venv."
    hold_window
    exit 1
  fi
fi

echo "Installing the tools this program needs. The first time can take a few minutes..."
if ! .venv/bin/python -m pip install -r requirements.txt; then
  echo "Could not install the tools. Check your internet connection and try again."
  hold_window
  exit 1
fi

echo
.venv/bin/python scrape.py
status=$?
echo
if [ "$status" -eq 0 ]; then
  echo "Done. Open output/jobs.xlsx to see the jobs."
else
  echo "The search stopped. Read the messages above."
fi
hold_window
exit "$status"
