#!/bin/bash
# One-command start for macOS and Linux.
# On a Mac you can double-click start.command instead.
# When a terminal is open, scrape.py asks:
#   1. Search for jobs
#   2. Make a CV for one of these jobs
#   3. I don't have a CV yet - help me make one

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

# Skip pip when .venv/.requirements.sha256 matches the sha256 of requirements.txt.
hash_file=".venv/.requirements.sha256"
req_hash="$(.venv/bin/python -c 'import hashlib, pathlib; print(hashlib.sha256(pathlib.Path("requirements.txt").read_bytes()).hexdigest())')" || {
  echo "Could not read requirements.txt."
  hold_window
  exit 1
}
saved_hash=""
if [ -f "$hash_file" ]; then
  saved_hash="$(tr -d '[:space:]' < "$hash_file")"
fi
if [ -n "$saved_hash" ] && [ "$saved_hash" = "$req_hash" ]; then
  echo "The tools are already installed."
else
  echo "Installing the tools this program needs. The first time can take a few minutes..."
  if .venv/bin/python -m pip install -r requirements.txt; then
    printf '%s\n' "$req_hash" > "$hash_file"
  elif [ -f "$hash_file" ]; then
    echo "Could not update the tools (no internet?). Continuing with the ones already installed."
  else
    echo "Could not install the tools. Check your internet connection and try again."
    hold_window
    exit 1
  fi
fi

echo
.venv/bin/python scrape.py
status=$?
echo
if [ "$status" -eq 0 ]; then
  echo "Done. Open output/jobs.xlsx for jobs, or output/cv for a CV."
else
  echo "The search stopped. Read the messages above."
fi
hold_window
exit "$status"
