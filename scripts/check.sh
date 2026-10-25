#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
"${WORKBENCH_PYTHON:-python3}" -m unittest discover -s tests -v
if command -v node >/dev/null 2>&1; then
  node --check static/app.js
fi
