#!/usr/bin/env python3
"""Lightweight Playwright / Headless DOM Snapshot & Automation Runner for Cortical."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from html.parser import HTMLParser


class SemanticDOMExtractor(HTMLParser):
    """Fallback zero-dependency semantic HTML extractor when Playwright binary is not installed."""

    def __init__(self) -> None:
        super().__init__()
        self.Interactive: list[dict[str, str]] = []
        self.headings: list[str] = []
        self._current_tag: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._current_tag = tag
        attr_map = {k: (v or "") for k, v in attrs}
        if tag in {"a", "button", "input", "select", "textarea"}:
            self.Interactive.append(
                {
                    "tag": tag,
                    "id": attr_map.get("id", ""),
                    "name": attr_map.get("name", ""),
                    "role": attr_map.get("role", ""),
                    "href": attr_map.get("href", ""),
                }
            )

    def handle_data(self, data: str) -> None:
        if self._current_tag in {"h1", "h2", "h3", "title"}:
            text = data.strip()
            if text:
                self.headings.append(text)


def run_snapshot(url: str, html_override: str | None = None) -> dict[str, object]:
    if html_override is not None:
        raw_html = html_override
    else:
        req = urllib.request.Request(url, headers={"User-Agent": "Cortical-Agent/0.1"})
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            raw_html = resp.read().decode("utf-8", errors="replace")

    parser = SemanticDOMExtractor()
    parser.feed(raw_html)
    return {
        "url": url,
        "headings": parser.headings[:25],
        "interactive_elements": parser.Interactive[:50],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--action", choices=["snapshot"], default="snapshot")
    args = ap.parse_args()
    print(json.dumps(run_snapshot(args.url), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
