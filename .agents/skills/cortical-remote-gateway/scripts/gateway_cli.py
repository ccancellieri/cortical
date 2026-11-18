#!/usr/bin/env python3
"""Standard cross-harness wrapper for Cortical optional Remote Gateway (CLI + HTTP + MCP)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cortical.cli import main  # noqa: E402

if __name__ == "__main__":
    os.environ.setdefault("CORTICAL_WIKI_DB", str(ROOT / ".cortical_data" / "wiki.db"))
    sys.exit(main(["--db", os.environ["CORTICAL_WIKI_DB"], "gateway", *sys.argv[1:]]))
