"""Zero-dependency Local Privacy Sanitizer & GDPR Anonymizer for Cortical.

Protects sensitive documents before any excerpt reaches a remote cloud LLM:
  1. Metadata stripping (OOXML `.docx`/`.xlsx`/`.pptx` `docProps`, PDF info tags)
  2. Consistent local pseudonymization (`[EMAIL_1]`, `[PHONE_1]`, `[SECRET_1]`, etc.)
     keeping the mapping table strictly local so remote LLMs preserve context
  3. Optional offline Local LLM-as-a-Sanitizer pass (Ollama) to rewrite
     contextual GDPR quasi-identifiers without sending raw text to the cloud
"""

from __future__ import annotations

import io
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("SECRET", re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,})\b")),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),
    ("TAX_ID", re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b")),
    ("PHONE", re.compile(r"(?<!\w)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)\d{3,4}[\s.-]?\d{3,4}(?!\w)")),
    ("IP", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("PERSON_NAME", re.compile(r"\b[A-Z][a-zà-ù]{2,15}\s+[A-Z][a-zà-ù]{2,15}\b")),
]

_NON_PERSON_BIGRAMS = {
    "omni route", "skill hub", "skill engine", "second brain", "merkle tree",
    "apple silicon", "claude code", "google chrome", "open ai", "open code",
    "privacy sanitizer", "token report", "macro graph", "united nations",
}

_OOXML_SUFFIXES = {".docx", ".xlsx", ".pptx"}
_METADATA_XML_PARTS = {"docProps/core.xml", "docProps/app.xml", "docProps/custom.xml"}


@dataclass
class SanitizeResult:
    """Result of local document sanitization."""

    sanitized_text: str
    mode: str
    stripped_metadata: list[str] = field(default_factory=list)
    pseudonym_map: dict[str, str] = field(default_factory=dict)
    llm_refined: bool = False

    def to_dict(self, include_map: bool = False) -> dict[str, Any]:
        out: dict[str, Any] = {
            "sanitized_text": self.sanitized_text,
            "mode": self.mode,
            "stripped_metadata": self.stripped_metadata,
            "entity_count": len(self.pseudonym_map),
            "llm_refined": self.llm_refined,
        }
        if include_map:
            out["pseudonym_map"] = self.pseudonym_map
        return out


def extract_text_and_strip_metadata(file_path: Path) -> tuple[str, list[str]]:
    """Extracts clean text from text/OOXML/PDF files while stripping author/company metadata."""
    p = Path(file_path)
    suffix = p.suffix.lower()
    stripped: list[str] = []

    if suffix in _OOXML_SUFFIXES:
        texts: list[str] = []
        with zipfile.ZipFile(p, "r") as zf:
            for name in zf.namelist():
                if name in _METADATA_XML_PARTS:
                    stripped.append(name)
                    continue
                if name.endswith(".xml") and (
                    name.startswith("word/document")
                    or name.startswith("xl/sharedStrings")
                    or name.startswith("ppt/slides/slide")
                ):
                    raw_xml = zf.read(name)
                    try:
                        root = ET.fromstring(raw_xml)
                        parts = [el.text.strip() for el in root.iter() if el.text and el.text.strip()]
                        if parts:
                            texts.append(" ".join(parts))
                    except ET.ParseError:
                        continue
        return ("\n".join(texts), stripped)

    raw_bytes = p.read_bytes()
    if suffix == ".pdf":
        raw_str = raw_bytes.decode("latin-1", errors="replace")
        for tag in ("Author", "Creator", "Producer", "Company", "Title", "Subject"):
            if re.search(rf"/{tag}\s*\(", raw_str):
                stripped.append(f"pdf:/{tag}")
        cleaned = re.sub(r"/(Author|Creator|Producer|Company)\s*\([^)]*\)", "", raw_str)
        chunks = re.findall(r"\(([^()]{3,200})\)", cleaned)
        return ("\n".join(chunks) if chunks else "", stripped)

    text = raw_bytes.decode("utf-8", errors="replace")
    # Strip common YAML/HTML author metadata headers
    for hdr in ("author:", "email:", "company:"):
        if hdr in text[:500].lower():
            stripped.append(f"header:{hdr.rstrip(':')}")
    text = re.sub(r"(?im)^(author|email|company)\s*:\s*.*$", "", text)
    return (text.strip(), stripped)


def pseudonymize_text(
    text: str,
    redact: bool = False,
    strip_categories: Optional[list[str]] = None,
    custom_terms: Optional[list[str]] = None,
) -> tuple[str, dict[str, str]]:
    """Replaces sensitive tokens & user `custom_terms` with `[EMAIL_1]` / `[CUSTOM_1]` or `[REDACTED]`."""
    mapping: dict[str, str] = {}
    counters: dict[str, int] = {}
    out = text
    allowed_cats = {c.upper() for c in strip_categories} if strip_categories is not None else None

    def _register(val: str, lbl: str) -> str:
        if redact:
            mapping[f"[REDACTED:{lbl}:{len(mapping)+1}]"] = val
            return "[REDACTED]"
        for token, orig in mapping.items():
            if orig == val:
                return token
        counters[lbl] = counters.get(lbl, 0) + 1
        token = f"[{lbl}_{counters[lbl]}]"
        mapping[token] = val
        return token

    if custom_terms and (allowed_cats is None or "CUSTOM" in allowed_cats):
        terms_clean = sorted({str(t).strip() for t in custom_terms if str(t).strip()}, key=len, reverse=True)
        for term in terms_clean:
            rx_custom = re.compile(re.escape(term), re.IGNORECASE)
            out = rx_custom.sub(lambda m: _register(m.group(0), "CUSTOM"), out)

    for label, rx in _PATTERNS:
        if allowed_cats is not None and label not in allowed_cats:
            continue
        def _repl(match: re.Match[str], lbl: str = label) -> str:
            val = match.group(0)
            if lbl == "PERSON_NAME" and val.lower() in _NON_PERSON_BIGRAMS:
                return val
            return _register(val, lbl)

        out = rx.sub(_repl, out)
    return (out, mapping)


def _default_local_sanitizer_llm(prompt: str, model: Optional[str] = None) -> str:
    """Runs offline Ollama as a privacy sanitizer (0 cloud bytes sent)."""
    from .config import load_cortical_config

    san_cfg = load_cortical_config().get("privacy_sanitizer") or {}
    base = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    chosen = model or os.environ.get("CORTICAL_SANITIZER_MODEL") or str(san_cfg.get("sanitizer_model") or "qwen2.5:1.5b")
    payload = {
        "model": chosen,
        "stream": False,
        "think": False,
        "keep_alive": "90s",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Sei un filtro privacy locale offline (GDPR). Riscrivi il testo rimuovendo o "
                    "generalizzando nomi propri di persona, indirizzi e quasi-identificatori "
                    "(es. ruoli unici in piccole località), preservando i segnaposto esistenti come "
                    "[EMAIL_1] e il significato tecnico. Restituisci SOLO il testo sanitizzato."
                ),
            },
            {"role": "user", "content": prompt[:6000]},
        ],
        "options": {"temperature": 0.1, "num_predict": 1200},
    }
    req = urllib.request.Request(
        f"{base}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=25.0) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return str((body.get("message") or {}).get("content") or "").strip()


def sanitize_file(
    file_path: Path,
    *,
    redact: bool = False,
    use_local_llm: bool = False,
    llm_fn: Optional[Callable[[str], str]] = None,
    model: Optional[str] = None,
    strip_metadata: bool = True,
    strip_categories: Optional[list[str]] = None,
    custom_terms: Optional[list[str]] = None,
) -> SanitizeResult:
    """Strips metadata, pseudonymizes/redacts identifiers, and optionally rewrites quasi-identifiers locally."""
    p = Path(file_path)
    if strip_metadata:
        raw_text, stripped = extract_text_and_strip_metadata(p)
    else:
        raw_text = p.read_text(encoding="utf-8", errors="replace")
        stripped = []
    cleaned, pmap = pseudonymize_text(
        raw_text,
        redact=redact,
        strip_categories=strip_categories,
        custom_terms=custom_terms,
    )
    llm_refined = False

    if use_local_llm and cleaned.strip():
        try:
            fn = llm_fn or (lambda pr: _default_local_sanitizer_llm(pr, model=model))
            rewritten = (fn(cleaned) or "").strip()
            if rewritten:
                cleaned = rewritten
                llm_refined = True
        except Exception:  # noqa: BLE001
            pass

    return SanitizeResult(
        sanitized_text=cleaned,
        mode="redacted" if redact else "pseudonymized",
        stripped_metadata=stripped,
        pseudonym_map=pmap,
        llm_refined=llm_refined,
    )


def sanitize_with_profile(
    file_path: Path,
    profile_name: str = "medium",
    *,
    config: Optional[dict[str, Any]] = None,
    llm_fn: Optional[Callable[[str], str]] = None,
) -> dict[str, Any]:
    """Applies an extensible privacy profile (`max_security`, `low`, `medium`, `max_context`, or custom)."""
    from .config import load_cortical_config

    cfg = config or load_cortical_config()
    san_cfg = cfg.get("privacy_sanitizer") or {}
    san_model = str(san_cfg.get("sanitizer_model") or "qwen2.5:1.5b")
    custom_terms = list(san_cfg.get("custom_terms") or [])
    enable_person = bool(san_cfg.get("enable_person_name_heuristic", True))

    profiles = cfg.get("privacy_profiles") or {}
    prof = dict(profiles.get(profile_name) or profiles.get("medium") or {})
    cats = list(prof.get("strip_categories") or [])
    if not enable_person and "PERSON_NAME" in cats:
        cats = [c for c in cats if c != "PERSON_NAME"]

    if prof.get("local_only"):
        if prof.get("allow_local_conclusions"):
            res = sanitize_file(
                file_path,
                redact=True,
                use_local_llm=True,
                llm_fn=llm_fn or (lambda txt: _default_local_sanitizer_llm(
                    f"Estrai SOLO conclusioni tecniche ad alto livello senza nomi, dati personali o dettagli del file:\n{txt}",
                    model=san_model,
                )),
                model=san_model,
                strip_metadata=True,
                strip_categories=cats if prof.get("strip_categories") is not None else None,
                custom_terms=custom_terms,
            )
            payload = res.to_dict(include_map=False)
            payload["profile"] = profile_name
            payload["local_only"] = True
            return payload
        return {
            "profile": profile_name,
            "local_only": True,
            "sanitized_text": "[LOCAL_ONLY: File blocked from remote cloud egress by privacy profile.]",
            "stripped_metadata": [],
            "entity_count": 0,
            "llm_refined": False,
        }

    res = sanitize_file(
        file_path,
        redact=bool(prof.get("redact", False)),
        use_local_llm=bool(prof.get("use_local_llm", False)),
        llm_fn=llm_fn,
        model=san_model,
        strip_metadata=bool(prof.get("strip_metadata", True)),
        strip_categories=cats if prof.get("strip_categories") is not None else None,
        custom_terms=custom_terms,
    )
    out = res.to_dict(include_map=False)
    if prof.get("summary_only") and len(out["sanitized_text"]) > 1200:
        out["sanitized_text"] = out["sanitized_text"][:1200].rstrip() + "\n... [summary_only truncated]"
    out["profile"] = profile_name
    out["local_only"] = False
    return out


def strip_ooxml_metadata_bytes(raw_bytes: bytes) -> bytes:
    """Returns a copy of an OOXML `.docx`/`.xlsx`/`.pptx` archive with `docProps` metadata removed."""
    in_buf = io.BytesIO(raw_bytes)
    out_buf = io.BytesIO()
    with zipfile.ZipFile(in_buf, "r") as zin, zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename in _METADATA_XML_PARTS:
                continue
            zout.writestr(item, zin.read(item.filename))
    return out_buf.getvalue()


def ensure_privacy_ignore_files(
    repo_root: Path,
    extra_patterns: Optional[list[str]] = None,
) -> list[str]:
    """Ensures `.geminiignore`, `.cursorignore`, and `.claudeignore` exclude private vault dirs from cloud upload."""
    root = Path(repo_root)
    patterns = [
        ".cortical_data/private_notes/",
        ".cortical_data/private_vault/",
        *(extra_patterns or []),
    ]
    marker_start = "# >>> cortical-privacy-vault >>>"
    marker_end = "# <<< cortical-privacy-vault <<<"
    block = "\n".join([marker_start, *dict.fromkeys(patterns), marker_end]) + "\n"
    updated: list[str] = []
    for fname in (".geminiignore", ".cursorignore", ".claudeignore"):
        fp = root / fname
        cur = fp.read_text(encoding="utf-8") if fp.is_file() else ""
        if marker_start in cur and marker_end in cur:
            new_txt = re.sub(
                re.escape(marker_start) + r".*?" + re.escape(marker_end) + r"\n?",
                block,
                cur,
                flags=re.DOTALL,
            )
        else:
            new_txt = cur.rstrip() + ("\n\n" if cur.strip() else "") + block
        if new_txt != cur:
            fp.write_text(new_txt, encoding="utf-8")
            updated.append(fname)
    return updated
