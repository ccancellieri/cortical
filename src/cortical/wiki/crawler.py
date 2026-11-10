"""Deterministic Parallel Merkle-Tree Crawler & 4-Tier Hierarchical Summarizer.

Features:
- Parallel leaf indexing via ThreadPoolExecutor.
- Deterministic SHA-256 content & bottom-up subtree hashing: unchanged files and directories
  are skipped in O(1) without re-summarizing.
- Generates 3 synthesis tiers (`light`, `medium`, `high`) + stores `max` (full raw text).
- Supports pluggable LLM/fixture summarizer callback with deterministic extractive fallback.
"""

from __future__ import annotations

import hashlib
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .db import AccessContext, CorticalWikiDB

SummarizerFn = Callable[[str, str, str], dict[str, str]]

DEFAULT_IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".cortical_data",
    "dist",
    "build",
}

TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".json",
    ".yaml",
    ".yml",
    ".sh",
    ".sql",
    ".toml",
    ".rst",
    ".html",
    ".css",
}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def deterministic_extractive_summarizer(
    rel_path: str, raw_text: str, node_type: str = "file"
) -> dict[str, str]:
    """Fast, deterministic 3-tier synthesis (`light`, `medium`, `high`) without LLM latency."""
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    headings = [ln.lstrip("# ").strip() for ln in lines if ln.startswith("#")]
    code_defs = [
        ln.strip()
        for ln in lines
        if re.match(r"^(class|def|async def|export|function|interface|type)\s+", ln)
    ]

    title = headings[0] if headings else Path(rel_path).name
    first_para = next(
        (ln for ln in lines if not ln.startswith("#") and len(ln) > 15),
        lines[0] if lines else "Empty node",
    )

    # Tier 1: LIGHT (~50 tokens)
    light = f"[{node_type.upper()}] {rel_path} — {title}: {first_para[:160]}"

    # Tier 2: MEDIUM (~250 tokens)
    outline = ", ".join((headings[1:6] + code_defs[:6])[:8]) or "standard content"
    medium_lines = [
        f"Path: {rel_path} ({node_type})",
        f"Title: {title}",
        f"Structure: {outline}",
        "Key Excerpt: " + " ".join(lines[:6])[:600],
    ]
    medium = "\n".join(medium_lines)

    # Tier 3: HIGH (~1000 tokens)
    high_lines = [
        f"=== HIGH-DEPTH SYNTHESIS: {rel_path} ===",
        f"Headings: {', '.join(headings[:15]) or 'None'}",
        f"Symbols/Definitions: {', '.join(code_defs[:20]) or 'None'}",
        "Detailed Content Digest:",
        "\n".join(lines[:45])[:3200],
    ]
    high = "\n".join(high_lines)

    return {
        "light": light,
        "medium": medium,
        "high": high,
    }


@dataclass
class CrawlStats:
    files_scanned: int = 0
    files_updated: int = 0
    files_skipped_unchanged: int = 0
    dirs_updated: int = 0
    dirs_skipped_unchanged: int = 0
    root_subtree_hash: str = ""


class DeterministicMerkleCrawler:
    """Bottom-up parallel Merkle-tree crawler maintaining `light`, `medium`, `high`, `max` tiers."""

    def __init__(
        self,
        db: CorticalWikiDB,
        summarizer: Optional[SummarizerFn] = None,
        max_workers: int = 4,
    ) -> None:
        self.db = db
        self.summarizer = summarizer or deterministic_extractive_summarizer
        self.max_workers = max_workers

    def crawl_directory(
        self,
        root_dir: str | Path,
        ctx: Optional[AccessContext] = None,
    ) -> CrawlStats:
        ctx = ctx or AccessContext()
        root_path = Path(root_dir).resolve()
        self.db.ensure_workspace(ctx, root_path=str(root_path), can_write=True)

        stats = CrawlStats()
        file_entries: list[tuple[str, str, Path]] = []  # (wiki_path, parent_wiki_path, fs_path)
        dir_children: dict[str, list[str]] = {"/": []}
        dir_parents: dict[str, Optional[str]] = {"/": None}

        for current_root, dirs, files in os.walk(root_path):
            dirs[:] = sorted(
                d for d in dirs if d not in DEFAULT_IGNORE_DIRS and not d.startswith(".")
            )
            rel_dir = Path(current_root).relative_to(root_path)
            wiki_dir = "/" if str(rel_dir) == "." else "/" + rel_dir.as_posix()
            dir_children.setdefault(wiki_dir, [])

            for d in dirs:
                child_wiki_dir = (
                    f"/{d}" if wiki_dir == "/" else f"{wiki_dir}/{d}"
                )
                dir_children[wiki_dir].append(child_wiki_dir)
                dir_children.setdefault(child_wiki_dir, [])
                dir_parents[child_wiki_dir] = wiki_dir

            for fname in sorted(files):
                if fname.startswith("."):
                    continue
                fpath = Path(current_root) / fname
                if fpath.suffix.lower() not in TEXT_EXTENSIONS:
                    continue
                wiki_file = f"/{fname}" if wiki_dir == "/" else f"{wiki_dir}/{fname}"
                dir_children[wiki_dir].append(wiki_file)
                file_entries.append((wiki_file, wiki_dir, fpath))

        # 1. Parallel processing of leaf files
        stats.files_scanned = len(file_entries)

        def _process_file(entry: tuple[str, str, Path]) -> tuple[str, str, bool, str]:
            wiki_file, parent_dir, fpath = entry
            raw_text = fpath.read_text(encoding="utf-8", errors="replace")
            c_hash = sha256_text(raw_text)
            existing = self.db.get_node_hash(ctx, wiki_file)
            if existing and existing[0] == c_hash:
                node_view = self.db.navigate(ctx, wiki_file, depth="light", include_children=False)
                return wiki_file, c_hash, False, node_view["content"]

            tiers = self.summarizer(wiki_file, raw_text, "file")
            self.db.upsert_merkle_node(
                ctx,
                path=wiki_file,
                parent_path=parent_dir,
                node_type="file",
                content_hash=c_hash,
                subtree_hash=c_hash,
                summary_light=tiers["light"],
                summary_medium=tiers["medium"],
                summary_high=tiers["high"],
                raw_content=raw_text,
            )
            return wiki_file, c_hash, True, tiers["light"]

        node_hashes: dict[str, str] = {}
        node_lights: dict[str, str] = {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            for wiki_file, c_hash, updated, light_sum in pool.map(_process_file, file_entries):
                node_hashes[wiki_file] = c_hash
                node_lights[wiki_file] = light_sum
                if updated:
                    stats.files_updated += 1
                else:
                    stats.files_skipped_unchanged += 1

        # 2. Bottom-up deterministic Merkle aggregation for directories
        sorted_dirs = sorted(
            dir_children.keys(),
            key=lambda p: (0 if p == "/" else p.count("/"), len(p)),
            reverse=True,
        )

        for wiki_dir in sorted_dirs:
            children = sorted(dir_children.get(wiki_dir, []))
            hash_payload = "|".join(f"{c}:{node_hashes.get(c, '')}" for c in children)
            subtree_hash = sha256_text(f"DIR:{wiki_dir}:{hash_payload}")
            node_hashes[wiki_dir] = subtree_hash

            existing = self.db.get_node_hash(ctx, wiki_dir)
            if existing and existing[1] == subtree_hash:
                stats.dirs_skipped_unchanged += 1
                existing_node = self.db.navigate(
                    ctx, wiki_dir, depth="light", include_children=False
                )
                node_lights[wiki_dir] = existing_node["content"]
                continue

            child_Rollup = "\n".join(
                f"- {node_lights.get(c, c)}" for c in children
            ) or "Empty directory"
            tiers = self.summarizer(wiki_dir, f"# Subtree {wiki_dir}\n{child_Rollup}", "dir")
            self.db.upsert_merkle_node(
                ctx,
                path=wiki_dir,
                parent_path=dir_parents.get(wiki_dir),
                node_type="dir",
                content_hash=subtree_hash,
                subtree_hash=subtree_hash,
                summary_light=tiers["light"],
                summary_medium=tiers["medium"],
                summary_high=tiers["high"],
                raw_content=child_Rollup,
            )
            node_lights[wiki_dir] = tiers["light"]
            stats.dirs_updated += 1

        stats.root_subtree_hash = node_hashes.get("/", "")
        return stats
