#!/usr/bin/env bash
# Cross-Platform Live Service Installer for Cortical (macOS launchd & Linux systemd)
# Copyright 2026 Carlo Cancellieri — Apache-2.0 License
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
WIKI_DB="$ROOT_DIR/.cortical_data/wiki.db"
PERM_DB="$ROOT_DIR/.cortical_data/permissions.db"
LOG_DIR="$ROOT_DIR/.cortical_data/logs"
PORT="${CORTICAL_PORT:-8765}"

mkdir -p "$LOG_DIR"

OS_NAME="$(uname -s)"

if [ "$OS_NAME" = "Darwin" ]; then
  PLIST_PATH="$HOME/Library/LaunchAgents/io.ccancellieri.cortical.plist"
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>io.ccancellieri.cortical</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON_BIN</string>
    <string>-m</string>
    <string>cortical.cli</string>
    <string>--db</string>
    <string>$WIKI_DB</string>
    <string>--perm-db</string>
    <string>$PERM_DB</string>
    <string>serve</string>
    <string>--host</string>
    <string>127.0.0.1</string>
    <string>--port</string>
    <string>$PORT</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONPATH</key>
    <string>$ROOT_DIR/src</string>
  </dict>
  <key>WorkingDirectory</key>
  <string>$ROOT_DIR</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/cortical.out.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/cortical.err.log</string>
</dict>
</plist>
EOF
  launchctl unload "$PLIST_PATH" 2>/dev/null || true
  launchctl load -w "$PLIST_PATH"
  echo "==> [macOS] Loaded launchd service io.ccancellieri.cortical on http://127.0.0.1:$PORT"
else
  SERVICE_DIR="$HOME/.config/systemd/user"
  mkdir -p "$SERVICE_DIR"
  SERVICE_FILE="$SERVICE_DIR/cortical.service"
  cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Cortical Live Agentic Harness, 4-Tier Second Brain & Voice Service
After=network.target

[Service]
Type=simple
WorkingDirectory=$ROOT_DIR
Environment=PYTHONPATH=$ROOT_DIR/src
ExecStart=$PYTHON_BIN -m cortical.cli --db $WIKI_DB --perm-db $PERM_DB serve --host 127.0.0.1 --port $PORT
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOF
  systemctl --user daemon-reload
  systemctl --user enable --now cortical.service
  echo "==> [Linux] Enabled and started systemd user service cortical.service on http://127.0.0.1:$PORT"
fi
