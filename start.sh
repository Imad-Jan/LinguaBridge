#!/usr/bin/env bash
set -euo pipefail

if [ ! -x ".venv/bin/python" ]; then
  echo "Run ./setup.sh first."
  exit 1
fi

.venv/bin/python launcher.py

