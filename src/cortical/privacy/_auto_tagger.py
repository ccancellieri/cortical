"""Deterministic zero-LLM auto-tagging for local Privacy Vault documents."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

_EXT_TAGS: dict[str, tuple[str, ...]] = {
    "ocr": ("png", "jpg", "jpeg", "webp", "tiff", "tif"),
    "contract": ("docx", "doc"),
    "finance": ("xls", "xlsx", "csv"),
    "code": ("py", "js", "ts", "tsx", "jsx", "rs", "go", "java", "c", "cpp", "h", "yaml", "yml", "toml", "json"),
    "notes": ("md", "txt", "rst"),
}

_KEYWORD_TAGS: dict[str, tuple[str, ...]] = {
    "ocr": ("ocr", "scan", "screenshot", "ricevuta_img"),
    "cv": ("curriculum", "resume", "candidato", "cover_letter"),
    "contract": ("contract", "contratto", "agreement", "accordo", "nda"),
    "invoice": ("invoice", "fattura", "bill", "ricevuta", "receipt"),
    "finance": ("financial", "finanza", "budget", "costo", "spesa", "iban"),
    "code": ("source", "src", "def ", "class ", "import ", "function "),
    "notes": ("note", "memo", "ricorda", "meeting", "minutes"),
    "identity": ("id_card", "passport", "carta_identita", "identity", "codice_fiscale", "personale"),
}


def auto_detect_tags(
    path_or_text: str | Path,
    *,
    task_tags: Optional[list[str]] = None,
    content_hint: str = "",
) -> list[str]:
    """Deterministically detects 1-3 document tags from filename/extension/text heuristics."""
    if task_tags:
        return list(dict.fromkeys(str(t).strip().lower().lstrip("#") for t in task_tags if str(t).strip()))

    raw = str(path_or_text or "")
    is_multiline = "\n" in raw or len(raw) >= 240
    exts: set[str] = set()
    stem = ""
    if not is_multiline:
        try:
            p = Path(raw)
            exts = {s.lstrip(".").lower() for s in p.suffixes if s}
            stem = p.stem.lower()
        except Exception:
            stem = raw.lower()

    haystack = f"{stem} {raw[:500] if is_multiline else ''} {content_hint[:500]}".lower()
    detected: list[str] = []
    for tag, ext_set in _EXT_TAGS.items():
        if exts.intersection(ext_set):
            detected.append(tag)
    for tag, kws in _KEYWORD_TAGS.items():
        if tag not in detected and any(kw in haystack for kw in kws):
            detected.append(tag)
    return detected[:4]


def get_default_tags_for_path(path_or_text: str | Path, *, content_hint: str = "") -> list[str]:
    """Returns compact default tags (up to 3) when no explicit task_tags were given."""
    return auto_detect_tags(path_or_text, task_tags=None, content_hint=content_hint)[:3]
