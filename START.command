#!/bin/sh
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  printf '\nPython 3.11+ is required. Install Python, then run python3 start.py.\n'
  read -r answer
  exit 1
fi
python3 start.py
