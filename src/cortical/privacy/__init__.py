"""Dynamic privacy sanitizer (`auto` | `fail_closed` | `fail_open`), local JSON NER & 3-channel Vault."""

from .sanitizer import (
    FailClosedError,
    classify_and_sanitize,
    detect_entities_local_llm,
    ensure_privacy_ignore_files,
    extract_text_and_strip_metadata,
    extract_text_from_bytes,
    pseudonymize_structured,
)
from .vault import VERIFIED_PRESEND_HARNESSES, PrivacyVault

__all__ = [
    "FailClosedError",
    "PrivacyVault",
    "VERIFIED_PRESEND_HARNESSES",
    "classify_and_sanitize",
    "detect_entities_local_llm",
    "ensure_privacy_ignore_files",
    "extract_text_and_strip_metadata",
    "extract_text_from_bytes",
    "pseudonymize_structured",
]
