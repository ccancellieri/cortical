"""Dynamic privacy sanitizer (`auto` | `fail_closed` | `fail_open`), local JSON NER & 3-channel Vault."""

from .brain import LocalBrain, build_3plus1_tiers
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
    "LocalBrain",
    "PrivacyVault",
    "VERIFIED_PRESEND_HARNESSES",
    "build_3plus1_tiers",
    "classify_and_sanitize",
    "detect_entities_local_llm",
    "ensure_privacy_ignore_files",
    "extract_text_and_strip_metadata",
    "extract_text_from_bytes",
    "pseudonymize_structured",
]
