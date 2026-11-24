"""Privacy-preserving local sanitizer with dynamic `auto` | `fail_closed` | `fail_open` policy & local JSON NER."""

from __future__ import annotations

import base64
import html
import json
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
import urllib.request
import zlib
from pathlib import Path
from typing import Any, Callable, Optional

_OOXML_SUFFIXES = {".docx", ".xlsx", ".pptx"}
_METADATA_XML_PARTS = {"docProps/core.xml", "docProps/app.xml", "docProps/custom.xml"}

_STRUCTURAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("SECRET", re.compile(r"\b(?:sk-[a-zA-Z0-9_-]{16,}|gh[pous]_[a-zA-Z0-9]{20,}|AKIA[0-9A-Z]{16}|Bearer\s+[A-Za-z0-9._-]{16,}|pplx-[A-Za-z0-9]{20,})\b")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),
    ("TAX_ID", re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b")),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("PHONE", re.compile(r"(?<!\w)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)\d{3,4}[\s.-]?\d{3,4}(?!\w)")),
    ("IP", re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")),
)

_SENSITIVE_FOLDER_HINTS = ("private", "secret", "vault", "hr", "contract", "finance", "invoice", "tax", "payroll", "medical", "gdpr", "pii")


class FailClosedError(RuntimeError):
    """Raised whenever a `fail_closed` sanitization or local NER check cannot guarantee safe output."""


def _unescape_pdf_literal(raw: bytes) -> str:
    txt = raw.decode("latin-1", errors="replace")
    txt = txt.replace(r"\\", "\x00").replace(r"\(", "(").replace(r"\)", ")")
    txt = txt.replace(r"\n", "\n").replace(r"\r", "\n").replace(r"\t", "\t")
    return txt.replace("\x00", "\\")


def _extract_pdf_text_stdlib(raw_bytes: bytes) -> str:
    """Pure-stdlib fallback extracting text from FlateDecode streams & PDF Tj/TJ text operators."""
    chunks: list[str] = []
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\n?endstream", raw_bytes, flags=re.S):
        payload = m.group(1)
        data = payload
        try:
            data = zlib.decompress(payload)
        except Exception:  # noqa: BLE001
            pass
        # Extract text-showing operators: (...) Tj and [(...) ...] TJ
        for op in re.finditer(rb"(\((?:\\.|[^\\()])*\))\s*Tj|\[((?:\\.|[^\[\]])*)\]\s*TJ", data, flags=re.S):
            if op.group(1):
                s = _unescape_pdf_literal(op.group(1)[1:-1])
                if s.strip():
                    chunks.append(s)
            elif op.group(2):
                parts = [
                    _unescape_pdf_literal(p.group(1))
                    for p in re.finditer(rb"\(((?:\\.|[^\\()])*)\)", op.group(2), flags=re.S)
                ]
                joined = "".join(parts).strip()
                if joined:
                    chunks.append(joined)
    if not chunks:
        cleaned = re.sub(rb"/(Author|Creator|Producer|Company|Title|Subject)\s*\([^)]*\)", b"", raw_bytes)
        for lit in re.finditer(rb"\(((?:\\.|[^\\()]){3,300})\)", cleaned):
            s = _unescape_pdf_literal(lit.group(1)).strip()
            if s and not s.startswith("/"):
                chunks.append(s)
    return "\n".join(chunks)


def _normalize_extracted_text(text: str) -> str:
    cleaned = "".join(ch for ch in text if ch in "\n\t\r" or ord(ch) >= 32)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
_VISION_ADAPTER: Optional[Callable[[bytes, str], str]] = None


def register_vision_adapter(fn: Optional[Callable[[bytes, str], str]]) -> None:
    """Registers a custom `(image_bytes, model) -> text` local OCR/vision adapter (used by tests & non-Ollama runners)."""
    global _VISION_ADAPTER
    _VISION_ADAPTER = fn


def ocr_image_local(image_bytes: bytes, *, model: Optional[str], config: Optional[dict[str, Any]] = None, timeout: float = 180.0) -> str:
    """Transcribes text from an image with a LOCAL vision model across Ollama or OpenAI-compatible local runners. Never contacts remote services."""
    if not model:
        raise FailClosedError(
            "No local vision model configured (@role:vision / privacy.vision_model). "
            "Tier-1 Zero-LLM Privacy Vault remains 100% active for MD/TXT/JSON/DOCX/XLSX/PPTX and selectable PDFs. "
            "For image or scanned-PDF OCR, configure @role:vision in settings.html using any local runner "
            "(Ollama, Unsloth Studio, LM Studio, llama.cpp, MLX, or vLLM)."
        )
    if _VISION_ADAPTER is not None:
        return str(_VISION_ADAPTER(image_bytes, model))

    from ..config import resolve_active_runner_endpoint

    r_name, r_type, _ = resolve_active_runner_endpoint(config, v1=False)
    b64_img = base64.b64encode(image_bytes).decode("ascii")
    ocr_prompt = "Transcribe ALL text visible in this image verbatim, line by line. Output only the text."

    if r_type == "ollama":
        _, _, base = resolve_active_runner_endpoint(config, runner_name=r_name, v1=False)
        endpoint_url = f"{base}/api/chat"
        body = json.dumps({
            "model": model,
            "stream": False,
            "messages": [{
                "role": "user",
                "content": ocr_prompt,
                "images": [b64_img],
            }],
        }).encode("utf-8")
    else:
        _, _, v1_base = resolve_active_runner_endpoint(config, runner_name=r_name, v1=True)
        endpoint_url = f"{v1_base}/chat/completions"
        body = json.dumps({
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": ocr_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_img}"}},
                ],
            }],
            "max_tokens": 2048,
            "temperature": 0.0,
        }).encode("utf-8")

    req = urllib.request.Request(endpoint_url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            detail = str(exc)
        if "multimodal" in detail.lower() or "vision" in detail.lower() or "image" in detail.lower():
            raise FailClosedError(
                f"Model '{model}' on local runner '{r_name}' lacks multimodal vision support ({detail[:140]}). "
                "Select a vision-capable model for @role:vision in settings.html (e.g. minicpm-ocr, qwen2.5vl, or an MLX/Unsloth VLM)."
            ) from exc
        raise FailClosedError(f"Local vision runner '{r_name}' ({endpoint_url}, model='{model}') HTTP {exc.code}: {detail or exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise FailClosedError(
            f"Local vision runner '{r_name}' ({endpoint_url}, model='{model}') is unavailable ({exc}). "
            "Tier-1 Zero-LLM Privacy Vault remains active for text/OOXML/selectable-PDF files. "
            "Start your local runner (Ollama, Unsloth Studio, LM Studio, llama.cpp, MLX, or vLLM) to process images."
        ) from exc

    if r_type == "ollama":
        return str(((data.get("message") or {}).get("content")) or "")
    choices = data.get("choices") or []
    return str((choices[0].get("message") or {}).get("content") or "") if choices else ""


def extract_text_and_strip_metadata(
    file_path: Path,
    *,
    vision_model: Optional[str] = None,
    config: Optional[dict[str, Any]] = None,
) -> tuple[str, list[str]]:
    """Extracts text from files/OOXML/PDF/images while removing author/company metadata tags."""
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
                        fallback = re.sub(r"<[^>]+>", " ", raw_xml.decode("utf-8", errors="replace"))
                        clean_fb = " ".join(html.unescape(fallback).split())
                        if clean_fb:
                            texts.append(clean_fb)
        return (_normalize_extracted_text("\n".join(texts)), stripped)

    raw_bytes = p.read_bytes()
    if suffix in _IMAGE_SUFFIXES:
        norm_img = _normalize_extracted_text(ocr_image_local(raw_bytes, model=vision_model, config=config))
        if len(re.sub(r"\s+", "", norm_img)) < 2:
            raise FailClosedError("Vision model found no readable text in the image.")
        return (norm_img, ["image:exif-dropped"])
    if suffix == ".pdf":
        raw_str = raw_bytes.decode("latin-1", errors="replace")
        for tag in ("Author", "Creator", "Producer", "Company", "Title", "Subject"):
            if re.search(rf"/{tag}\s*\(", raw_str):
                stripped.append(f"pdf:/{tag}")

        extracted = ""
        pdftotext_bin = shutil.which("pdftotext")
        mutool_bin = shutil.which("mutool")
        if pdftotext_bin:
            proc = subprocess.run(
                [pdftotext_bin, "-layout", "-nopgbrk", str(p), "-"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                extracted = proc.stdout
        if not extracted.strip() and mutool_bin:
            proc = subprocess.run(
                [mutool_bin, "draw", "-F", "txt", str(p)],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                extracted = proc.stdout
        if not extracted.strip():
            extracted = _extract_pdf_text_stdlib(raw_bytes)

        norm = _normalize_extracted_text(extracted)
        if len(re.sub(r"\s+", "", norm)) < 5 and vision_model and shutil.which("pdftoppm"):
            with tempfile.TemporaryDirectory() as tdir:
                subprocess.run(
                    [shutil.which("pdftoppm"), "-r", "110", "-png", "-l", "8", str(p), str(Path(tdir) / "pg")],
                    capture_output=True, timeout=60, check=False,
                )
                pages = [ocr_image_local(f.read_bytes(), model=vision_model, config=config) for f in sorted(Path(tdir).glob("pg*.png"))]
            norm = _normalize_extracted_text("\n\n".join(pages))
            stripped.append("pdf:scanned-ocr")
        if len(re.sub(r"\s+", "", norm)) < 5:
            raise FailClosedError(
                "PDF contains no extractable text layer (scanned/image-only PDF). Run local OCR first or convert to text."
            )
        return (norm, stripped)

    text = raw_bytes.decode("utf-8", errors="replace")
    for hdr in ("author:", "email:", "company:"):
        if hdr in text[:500].lower():
            stripped.append(f"header:{hdr.rstrip(':')}")
    text = re.sub(r"(?im)^(author|email|company)\s*:\s*.*$", "", text)
    return (_normalize_extracted_text(text), stripped)


def extract_text_from_bytes(filename: str, raw_bytes: bytes, **kw: Any) -> tuple[str, list[str]]:
    """Extracts text and strips metadata from in-memory bytes while preserving extension handlers."""
    safe_name = Path(filename or "upload.txt").name or "upload.txt"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / safe_name
        tmp_path.write_bytes(raw_bytes)
        return extract_text_and_strip_metadata(tmp_path, **kw)


def pseudonymize_structured(
    text: str,
    *,
    redact: bool = False,
    strip_categories: Optional[list[str]] = None,
    custom_terms: Optional[list[str]] = None,
    extra_entities: Optional[list[dict[str, str]]] = None,
    keep_terms: Optional[list[str]] = None,
    pseudonym_state: Optional[dict[str, Any]] = None,
) -> tuple[str, dict[str, str]]:
    """Replaces structural PII, `custom_terms`, and verified NER entities without false-positive bigram regexes."""
    allowed = {c.upper() for c in strip_categories} if strip_categories else None
    mapping: dict[str, str] = {}
    rev: dict[str, str] = pseudonym_state.setdefault("rev", {}) if pseudonym_state is not None else {}
    counters: dict[str, int] = pseudonym_state.setdefault("counters", {}) if pseudonym_state is not None else {}

    keep = {str(k).strip().lower() for k in (keep_terms or []) if str(k).strip()}

    def _token_for(cat: str, raw_val: str) -> str:
        if raw_val.strip().lower() in keep:
            return raw_val
        if raw_val in rev:
            tok = rev[raw_val]
            if redact:
                mapping[f"{cat}_{len(mapping) + 1}"] = raw_val
            else:
                mapping[tok] = raw_val
            return tok
        if redact:
            rev[raw_val] = "[REDACTED]"
            mapping[f"{cat}_{len(mapping) + 1}"] = raw_val
            return "[REDACTED]"
        counters[cat] = counters.get(cat, 0) + 1
        tok = f"[{cat}_{counters[cat]}]"
        rev[raw_val] = tok
        mapping[tok] = raw_val
        return tok

    out = text
    # 1. Exact user custom terms first
    if custom_terms and (allowed is None or "CUSTOM" in allowed):
        for term in sorted({str(t).strip() for t in custom_terms if str(t).strip()}, key=len, reverse=True):
            pat = re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)
            out = pat.sub(lambda m: _token_for("CUSTOM", m.group(0)), out)

    # 2. Local JSON NER entities (verified verbatim spans)
    for ent in (extra_entities or []):
        raw_ent = str(ent.get("text") or "").strip()
        cat = str(ent.get("category") or "PERSON_NAME").upper()
        if raw_ent and (allowed is None or cat in allowed):
            pat = re.compile(rf"(?<!\w){re.escape(raw_ent)}(?!\w)")
            out = pat.sub(lambda m, c=cat: _token_for(c, m.group(0)), out)

    # 3. Structural deterministic PII (zero technical false positives)
    for cat, regex in _STRUCTURAL_PATTERNS:
        if allowed is not None and cat not in allowed:
            continue
        out = regex.sub(lambda m, c=cat: _token_for(c, m.group(0)), out)

    return (out, mapping)


def detect_entities_local_llm(
    text: str,
    *,
    llm_fn: Optional[Callable[[str], str]] = None,
    model: Optional[str] = None,
    config: Optional[dict[str, Any]] = None,
) -> list[dict[str, str]]:
    """Extracts person/org names as strict verified JSON using a compact offline local LLM (1.5B-3B)."""
    if not text.strip():
        return []
    prompt = (
        "Extract ONLY real person full names (PERSON_NAME) and private company/client names (ORG) from the text below. "
        "Do NOT include programming terms, file names, headers, or software libraries. "
        'Reply ONLY with JSON: {"entities": [{"text": "Exact Span", "category": "PERSON_NAME"}]} .\n\n'
        f"TEXT:\n{text[:3000]}"
    )
    if llm_fn is not None:
        raw_reply = llm_fn(prompt)
    else:
        from ..config import invoke_configured_runner
        from ..roles import normalize_role_or_model

        raw_reply = invoke_configured_runner(
            prompt,
            system_prompt="You are a strict GDPR NER extractor. Output valid JSON only.",
            config=config,
            model_override=normalize_role_or_model(model, config, default_role="ner"),
            max_tokens=300,
            timeout=12.0,
            role="privacy_ner",
            record_telemetry=False,
        )
    raw_s = str(raw_reply or "").strip()
    m_json = re.search(r"(\{.*\}|\[.*\])", raw_s, flags=re.S)
    if not m_json:
        raise FailClosedError("Local NER returned non-JSON response")
    payload = json.loads(m_json.group(0))
    entities = payload if isinstance(payload, list) else payload.get("entities")
    if not isinstance(entities, list):
        raise FailClosedError("Local NER JSON missing 'entities' list")
    verified: list[dict[str, str]] = []
    for item in entities:
        if not isinstance(item, dict):
            continue
        span = str(item.get("text") or "").strip()
        cat = str(item.get("category") or "PERSON_NAME").strip().upper()
        if span and len(span) >= 3 and span in text:
            verified.append({"text": span, "category": cat if cat in {"PERSON_NAME", "ORG"} else "PERSON_NAME"})
    return verified


def classify_and_sanitize(
    text_or_path: str | Path,
    *,
    policy: str = "auto",
    profile: str = "medium",
    custom_terms: Optional[list[str]] = None,
    use_local_ner: bool = False,
    llm_fn: Optional[Callable[[str], str]] = None,
    model: Optional[str] = None,
    config: Optional[dict[str, Any]] = None,
    vision_model: Optional[str] = None,
    keep_terms: Optional[list[str]] = None,
    pseudonym_state: Optional[dict[str, Any]] = None,
    preserve_pseudonyms: bool = False,
) -> dict[str, Any]:
    """Classifies content sensitivity dynamically (`auto` | `fail_closed` | `fail_open`) and sanitizes fail-safely."""
    eff_policy = policy.strip().lower()
    if eff_policy not in {"auto", "fail_closed", "fail_open"}:
        raise ValueError(f"Unsupported privacy policy: {policy}")

    path_hint = ""
    stripped_meta: list[str] = []
    try:
        p = Path(text_or_path) if not isinstance(text_or_path, str) or ("\n" not in text_or_path and len(text_or_path) < 260 and Path(text_or_path).is_file()) else None
        if p is not None and p.is_file():
            path_hint = str(p).lower()
            raw_text, stripped_meta = extract_text_and_strip_metadata(p, vision_model=vision_model, config=config)
        else:
            raw_text = str(text_or_path)
    except Exception as exc:
        if eff_policy == "fail_open":
            return {
                "resolved_policy": "fail_open",
                "profile": profile,
                "sanitized_text": "",
                "stripped_metadata": [],
                "entity_count": 0,
                "local_only": False,
                "requires_confirmation": False,
                "error": str(exc),
            }
        if isinstance(exc, FailClosedError):
            raise
        raise FailClosedError(f"Failed to read/extract content cleanly: {exc}") from exc

    # Inspect sensitivity signals
    pre_text, pre_map = pseudonymize_structured(raw_text, redact=False, custom_terms=custom_terms, keep_terms=keep_terms)
    path_sensitive = any(h in path_hint for h in _SENSITIVE_FOLDER_HINTS)
    sensitive_detected = bool(pre_map or stripped_meta or path_sensitive)

    if eff_policy == "auto":
        resolved_policy = "fail_closed" if (sensitive_detected or profile == "max_security") else "fail_open"
    else:
        resolved_policy = eff_policy

    ner_entities: list[dict[str, str]] = []
    ner_used = False
    if use_local_ner and (resolved_policy == "fail_closed" or profile in {"max_security", "low", "medium"}):
        try:
            ner_entities = detect_entities_local_llm(raw_text, llm_fn=llm_fn, model=model, config=config)
            ner_used = True
        except Exception as exc:
            if resolved_policy == "fail_closed":
                raise FailClosedError(f"Fail-closed abort: local NER failed ({exc})") from exc

    redact = False if preserve_pseudonyms else (profile in {"max_security", "low"})
    if profile == "max_context" and resolved_policy == "fail_open" and not preserve_pseudonyms:
        final_text, mapping = raw_text, {}
    else:
        final_text, mapping = pseudonymize_structured(
            raw_text,
            redact=redact,
            custom_terms=custom_terms,
            extra_entities=ner_entities,
            keep_terms=keep_terms,
            pseudonym_state=pseudonym_state,
        )

    by_category: dict[str, int] = {}
    for tok in mapping:
        clean_tok = tok.strip("[]")
        cat = clean_tok.rsplit("_", 1)[0] if "_" in clean_tok else clean_tok
        by_category[cat] = by_category.get(cat, 0) + 1
    if stripped_meta:
        by_category["METADATA"] = len(stripped_meta)

    return {
        "resolved_policy": resolved_policy,
        "requested_policy": eff_policy,
        "profile": profile,
        "local_only": profile == "max_security",
        "requires_confirmation": eff_policy == "auto" and sensitive_detected,
        "sensitive_signals": len(pre_map) + len(stripped_meta) + (1 if path_sensitive else 0),
        "sanitized_text": final_text,
        "stripped_metadata": stripped_meta,
        "metadata_stripped_count": len(stripped_meta),
        "entity_count": len(mapping),
        "entities_by_category": by_category,
        "ner_used": ner_used,
        "pseudonym_map": mapping,
    }


def ensure_privacy_ignore_files(repo_root: Path) -> list[Path]:
    """Ensures `.geminiignore`, `.cursorignore`, and `.claudeignore` exclude private vault files."""
    root = Path(repo_root)
    patterns = [".cortical_data/private_vault/", ".cortical_data/outbox/", "*.key", "*.pem"]
    updated: list[Path] = []
    for fname in (".geminiignore", ".cursorignore", ".claudeignore"):
        target = root / fname
        existing = target.read_text(encoding="utf-8") if target.is_file() else ""
        lines = [ln.rstrip() for ln in existing.splitlines() if ln.strip()]
        changed = False
        for pat in patterns:
            if pat not in lines:
                lines.append(pat)
                changed = True
        if changed or not target.is_file():
            target.write_text("\n".join(lines) + "\n", encoding="utf-8")
            updated.append(target)
    return updated
