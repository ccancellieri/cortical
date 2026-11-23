#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"

echo "==> Cortical Zero-Friction Bootstrap (Python 3.10+ stdlib only)"

"$PYTHON_BIN" -c 'import sys; assert sys.version_info >= (3, 10), f"Python 3.10+ required, found {sys.version}"'

if [ ! -d "$VENV_DIR" ]; then
  echo "==> Creating virtual environment at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

VENV_PY="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

echo "==> Installing cortical-agent in editable mode (--no-deps)"
if [ -x "$VENV_PIP" ] && "$VENV_PIP" install --no-deps --no-build-isolation -e "$ROOT_DIR" >/dev/null 2>&1; then
  echo "    Installed via pip editable (--no-deps --no-build-isolation)"
else
  echo "    Offline stdlib fallback: wiring .pth + native entry-points in $VENV_DIR/bin"
  SITE_PKG="$("$VENV_PY" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
  printf '%s\n' "$ROOT_DIR/src" > "$SITE_PKG/cortical_editable.pth"
  cat > "$VENV_DIR/bin/cortical" <<EOF
#!$VENV_PY
import sys
from cortical.cli import main
if __name__ == "__main__":
    raise SystemExit(main())
EOF
  cat > "$VENV_DIR/bin/cortical-mcp" <<EOF
#!$VENV_PY
import sys
from cortical.mcp_server import main
if __name__ == "__main__":
    raise SystemExit(main())
EOF
  chmod +x "$VENV_DIR/bin/cortical" "$VENV_DIR/bin/cortical-mcp"
fi

echo "==> Verifying native CLI entry-point (no PYTHONPATH needed)"
"$VENV_DIR/bin/cortical" --help >/dev/null
"$VENV_DIR/bin/cortical" doctor --json >/dev/null

echo ""
echo "Cortical is ready! Activate or invoke directly:"
echo "  source .venv/bin/activate && cortical --help"
echo "  $VENV_DIR/bin/cortical init --yes"
echo "  $VENV_DIR/bin/cortical cortical --serve --open"
