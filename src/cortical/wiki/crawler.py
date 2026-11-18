"""Deterministic Parallel Merkle-Tree Crawler & 4-Tier Hierarchical Summarizer.

Features:
- Parallel leaf indexing via ThreadPoolExecutor.
- Deterministic SHA-256 content & bottom-up subtree hashing: unchanged files and directories
  are skipped in O(1) without re-summarizing.
- Generates 3 synthesis tiers (`light`, `medium`, `high`) + stores `max` (full raw text).
- Supports pluggable LLM/fixture summarizer callback with deterministic extractive fallback.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import urllib.request
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


def _extract_python_ast_summary(raw_text: str) -> tuple[str, list[str], list[str]]:
    """Extracts module docstring, symbol signatures, and docstrings via stdlib `ast`."""
    try:
        tree = ast.parse(raw_text)
    except SyntaxError:
        return ("", [], [])
    mod_doc = (ast.get_docstring(tree) or "").strip().splitlines()[0] if ast.get_docstring(tree) else ""
    defs: list[str] = []
    docs: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            cdoc = (ast.get_docstring(node) or "").strip().splitlines()[0] if ast.get_docstring(node) else ""
            methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))][:8]
            sig = f"class {node.name}({', '.join(methods)})" if methods else f"class {node.name}"
            defs.append(sig)
            if cdoc:
                docs.append(f"{node.name}: {cdoc[:100]}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [a.arg for a in node.args.args if a.arg != "self"][:5]
            prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
            defs.append(f"{prefix}{node.name}({', '.join(args)})")
            fdoc = (ast.get_docstring(node) or "").strip().splitlines()[0] if ast.get_docstring(node) else ""
            if fdoc:
                docs.append(f"{node.name}: {fdoc[:100]}")
    return (mod_doc, defs, docs)


def deterministic_extractive_summarizer(
    rel_path: str, raw_text: str, node_type: str = "file"
) -> dict[str, str]:
    """Fast, deterministic 3-tier synthesis (`light`, `medium`, `high`) using AST + headings."""
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    headings = [ln.lstrip("# ").strip() for ln in lines if ln.startswith("#")]
    mod_doc, ast_defs, ast_docs = (
        _extract_python_ast_summary(raw_text) if rel_path.endswith(".py") and node_type == "file" else ("", [], [])
    )
    code_defs = ast_defs or [
        ln.strip()
        for ln in lines
        if re.match(r"^(class|def|async def|export|function|interface|type)\s+", ln)
    ]

    title = headings[0] if headings else Path(rel_path).name
    first_para = mod_doc or next(
        (ln for ln in lines if not ln.startswith("#") and len(ln) > 15),
        lines[0] if lines else "Empty node",
    )

    # Tier 1: LIGHT (~50 tokens)
    light = f"[{node_type.upper()}] {rel_path} — {title}: {first_para[:160]}"

    # Tier 2: MEDIUM (~250 tokens)
    outline = ", ".join((headings[1:6] + code_defs[:8])[:10]) or "standard content"
    doc_notes = "; ".join(ast_docs[:6]) if ast_docs else " ".join(lines[:6])[:500]
    medium_lines = [
        f"Path: {rel_path} ({node_type})",
        f"Title: {title}",
        f"Structure: {outline}",
        f"Key Summary: {doc_notes[:600]}",
    ]
    medium = "\n".join(medium_lines)

    # Tier 3: HIGH (~1000 tokens)
    high_lines = [
        f"=== HIGH-DEPTH SYNTHESIS: {rel_path} ===",
        f"Headings: {', '.join(headings[:15]) or 'None'}",
        f"Symbols/Definitions: {', '.join(code_defs[:25]) or 'None'}",
    ]
    if ast_docs:
        high_lines.append("Docstrings:\n" + "\n".join(f"- {d}" for d in ast_docs[:20]))
    high_lines.append("Detailed Content Digest:")
    high_lines.append("\n".join(lines[:45])[:3000])
    high = "\n".join(high_lines)

    return {
        "light": light,
        "medium": medium,
        "high": high,
    }


def make_ollama_3tier_summarizer(
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> SummarizerFn:
    """Returns a local-Ollama 3-tier concept summarizer with deterministic AST fallback."""
    chosen = model or os.environ.get("CORTICAL_CRAWL_MODEL", "qwen3.5:9b-q3_k_xl")
    root = (base_url or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434").strip().rstrip("/")

    def _summarize(rel_path: str, raw_text: str, node_type: str = "file") -> dict[str, str]:
        base = deterministic_extractive_summarizer(rel_path, raw_text, node_type)
        if node_type != "file" or len(raw_text) < 200:
            return base
        prompt = (
            f"File: {rel_path}\nSintetizza in JSON con chiavi `light` (max 35 parole), "
            f"`medium` (max 140 parole: scopo, simboli, dipendenze) e `high` (max 350 parole):\n\n"
            f"{base['high'][:2800]}"
        )
        try:
            req = urllib.request.Request(
                f"{root}/api/chat",
                data=json.dumps({
                    "model": chosen,
                    "stream": False,
                    "think": False,
                    "format": "json",
                    "messages": [{"role": "user", "content": prompt}],
                    "options": {"temperature": 0.1, "num_predict": 450},
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                txt = (json.loads(resp.read().decode("utf-8")).get("message") or {}).get("content", "")
            parsed = json.loads(txt)
            if isinstance(parsed, dict) and parsed.get("light") and parsed.get("medium"):
                return {
                    "light": str(parsed["light"])[:400],
                    "medium": str(parsed["medium"])[:1400],
                    "high": str(parsed.get("high") or base["high"])[:3600],
                }
        except Exception:  # noqa: BLE001
            pass
        return base

    return _summarize


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
