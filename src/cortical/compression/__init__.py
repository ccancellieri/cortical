"""Deterministic lossless compression (TOON, compact JSON, logs, YAML/CSV/XML) & budget fitting."""

from .engine import compress_structured, fit_to_token_budget
from .toon import decode_toon, encode_toon

__all__ = [
    "compress_structured",
    "decode_toon",
    "encode_toon",
    "fit_to_token_budget",
]
