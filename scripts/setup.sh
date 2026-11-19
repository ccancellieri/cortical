#!/usr/bin/env bash
# Cortical One-Shot Cross-Platform Setup (macOS & Linux)
# Copyright 2026 Carlo Cancellieri — Apache-2.0 License
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "==> [1/3] Creating isolated Python virtual environment (.venv)..."
if python3 -m venv .venv 2>/dev/null; then
  .venv/bin/pip install --upgrade pip --quiet 2>/dev/null || true
  .venv/bin/pip install -e . --quiet 2>/dev/null || true
else
  echo "    [info] python3-venv ensurepip not installed; creating stdlib-only .venv (--without-pip)..."
  rm -rf .venv
  python3 -m venv --without-pip .venv
fi

SITE_PKGS="$(".venv/bin/python" -c 'import site; print(site.getsitepackages()[0])')"
mkdir -p "$SITE_PKGS"
echo "$ROOT_DIR/src" > "$SITE_PKGS/cortical.pth"

cat > .venv/bin/cortical <<EOF
#!/usr/bin/env bash
exec "$ROOT_DIR/.venv/bin/python" -m cortical.cli "\$@"
EOF
cat > .venv/bin/cortical-mcp <<EOF
#!/usr/bin/env bash
exec "$ROOT_DIR/.venv/bin/python" -m cortical.mcp_server "\$@"
EOF
chmod +x .venv/bin/cortical .venv/bin/cortical-mcp

echo "==> [2/3] Running Cortical Hardware Preflight & Composed OSS Tool Check..."
.venv/bin/python -m cortical.cli doctor --out-dir "$ROOT_DIR/.pi" --repo-root "$ROOT_DIR"

echo "==> [3/3] Exporting Static Dashboard (html/) & Dry-Run Sync Plan..."
.venv/bin/python -m cortical.cli dashboard --out-dir "$ROOT_DIR/html"
.venv/bin/python -m cortical.cli sync --dry-run

echo "Setup complete! Run '.venv/bin/cortical sync' to configure your harnesses or '.venv/bin/cortical dashboard --open'."
