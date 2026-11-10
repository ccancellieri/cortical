#!/usr/bin/env bash
# Cortical One-Shot Cross-Platform Setup (macOS & Linux)
# Copyright 2026 Carlo Cancellieri — Apache-2.0 License
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "==> [1/4] Creating isolated Python virtual environment (.venv)..."
if python3 -m venv .venv 2>/dev/null; then
  .venv/bin/pip install --upgrade pip --quiet 2>/dev/null || true
  .venv/bin/pip install -e . --quiet 2>/dev/null || true
else
  echo "    [info] python3-venv ensurepip not installed; creating stdlib-only .venv (--without-pip)..."
  rm -rf .venv
  python3 -m venv --without-pip .venv
fi

# Ensure src/ is always importable inside .venv even without pip/setuptools
SITE_PKGS="$(".venv/bin/python" -c 'import site; print(site.getsitepackages()[0])')"
mkdir -p "$SITE_PKGS"
echo "$ROOT_DIR/src" > "$SITE_PKGS/cortical.pth"

# Create convenient CLI wrappers in .venv/bin
cat > .venv/bin/cortical <<EOF
#!/usr/bin/env bash
exec "$ROOT_DIR/.venv/bin/python" -m cortical.cli "\$@"
EOF
cat > .venv/bin/cortical-wiki-mcp <<EOF
#!/usr/bin/env bash
exec "$ROOT_DIR/.venv/bin/python" -m cortical.wiki.mcp_server "\$@"
EOF
chmod +x .venv/bin/cortical .venv/bin/cortical-wiki-mcp

echo "==> [2/4] Running Cortical Hardware Auto-Profiler & Endpoint Discovery..."
.venv/bin/python -m cortical.cli doctor --out-dir "$ROOT_DIR/.pi" --repo-root "$ROOT_DIR"

echo "==> [3/4] Indexing workspace into 4-Tier Merkle Second Brain..."
.venv/bin/python -m cortical.cli --db "$ROOT_DIR/.cortical_data/wiki.db" crawl "$ROOT_DIR"

echo "==> [4/4] Setup complete! Generated .pi/mcp.json and .pi/hardware_profile.json."
