#!/bin/bash
# Sets up everything on first run, then starts My Dictation in your menu bar.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null; then
  echo "Python 3 is missing. Run: xcode-select --install  (then run this script again)"
  exit 1
fi
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))'; then
  echo "Python 3.9 or newer is needed. You have $(python3 --version)."
  exit 1
fi

if [ ! -d .venv ]; then
  echo "First run: installing (takes a minute)…"
  python3 -m venv .venv
fi
# Reinstall only when requirements.txt has changed.
if [ ! -f .venv/.installed ] || [ requirements.txt -nt .venv/.installed ]; then
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r requirements.txt
  # macOS notifications need a bundle identifier next to the Python executable.
  /usr/libexec/PlistBuddy -c 'Add :CFBundleIdentifier string "com.my-dictation"' .venv/bin/Info.plist >/dev/null 2>&1 || true
  touch .venv/.installed
fi

exec .venv/bin/python -u -m dictation
