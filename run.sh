#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo 'Run ./setup.sh first to create the Python environment.' >&2
  exit 1
fi
exec .venv/bin/python run.py "$@"
