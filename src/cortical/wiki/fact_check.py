"""2-Stage Citation & Claim Fact-Checking Engine (Pillar 2).

Stage 1 (Deterministic Grounding Check):
  Verifies that `source_path` exists in the workspace, matches ACL permissions,
  and that `quoted_span` actually appears in the raw document (normalized whitespace match).
Stage 2 (NLI / Decision Model Check):
  Uses an injectable NLI/LLM classifier (or JSON fixture / lexical entailment scorer)
  to verify that `quoted_span` entails `claim_text` rather than contradicting it.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from .db import AccessContext, CorticalWikiDB, DepthTier

NLIDecisionFn = Callable[[str, str], tuple[str, float]]


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def default_nli_decision_model(premise_span: str, hypothesis_claim: str) -> tuple[str, float]:
    """Deterministic local lexical/negation NLI scorer (replaceable by LLM/JSON fixture)."""
    norm_p = _normalize_ws(premise_span)
    norm_h = _normalize_ws(hypothesis_claim)

    h_tokens = {t for t in re.findall(r"[a-z0-9_]+", norm_h) if len(t) > 2}
    p_tokens = {t for t in re.findall(r"[a-z0-9_]+", norm_p) if len(t) > 2}
    if not h_tokens:
        return ("neutral", 0.5)

    overlap = len(h_tokens & p_tokens) / len(h_tokens)

    negations = {"not", "never", "no", "none", "false", "non", "mai", "nessuno"}
    p_neg = bool(negations & set(norm_p.split()))
    h_neg = bool(negations & set(norm_h.split()))

    # Numbers mismatch check (e.g., claiming 99% when span says 50%)
    p_nums = set(re.findall(r"\b\d+(?:\.\d+)?\b", norm_p))
    h_nums = set(re.findall(r"\b\d+(?:\.\d+)?\b", norm_h))
    if h_nums and p_nums and not (h_nums <= p_nums):
        return ("contradiction", 0.92)

    if overlap >= 0.45 and p_neg != h_neg:
        return ("contradiction", 0.88)

    if overlap >= 0.5:
        return ("entailment", round(min(0.99, 0.55 + overlap * 0.4), 3))

    return ("neutral", round(overlap, 3))


@dataclass
class VerificationResult:
    citation_id: str
    verdict: str  # 'verified' | 'refuted' | 'unverified'
    span_verified: bool
    nli_label: str
    nli_confidence: float
    source_hash: str
    reason: str


class CitationVerifier:
    """Verifies citations against the Merkle Second Brain and persists audit records."""

    def __init__(
        self,
        db: CorticalWikiDB,
        nli_model: Optional[NLIDecisionFn] = None,
        fixture_path: Optional[str | Path] = None,
    ) -> None:
        self.db = db
        self.fixture_map: dict[str, dict[str, Any]] = {}
        if fixture_path and Path(fixture_path).exists():
            data = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
            self.fixture_map = data.get("nli_decisions", {})
        self.nli_model = nli_model or self._resolve_nli

    def _resolve_nli(self, premise_span: str, hypothesis_claim: str) -> tuple[str, float]:
        if hypothesis_claim in self.fixture_map:
            entry = self.fixture_map[hypothesis_claim]
            return (entry["label"], float(entry["confidence"]))
        return default_nli_decision_model(premise_span, hypothesis_claim)

    def verify_and_record(
        self,
        ctx: AccessContext,
        *,
        claim_text: str,
        source_path: str,
        quoted_span: str,
    ) -> VerificationResult:
        citation_id = hashlib.sha256(
            f"{source_path}|{quoted_span}|{claim_text}".encode("utf-8")
        ).hexdigest()[:16]

        try:
            node = self.db.navigate(
                ctx, path=source_path, depth=DepthTier.MAX, include_children=False
            )
        except (KeyError, PermissionError) as exc:
            return VerificationResult(
                citation_id=citation_id,
                verdict="unverified",
                span_verified=False,
                nli_label="unverified",
                nli_confidence=0.0,
                source_hash="",
                reason=str(exc),
            )

        raw_doc = node.get("content", "")
        source_hash = node.get("content_hash", "")
        span_ok = bool(quoted_span.strip()) and (
            _normalize_ws(quoted_span) in _normalize_ws(raw_doc)
        )

        if not span_ok:
            verdict = "unverified"
            nli_label = "missing_span"
            nli_conf = 0.0
            reason = f"Quoted span not found verbatim in '{source_path}'."
        else:
            nli_label, nli_conf = self.nli_model(quoted_span, claim_text)
            if nli_label == "entailment" and nli_conf >= 0.65:
                verdict = "verified"
                reason = "Span exists in source and entails the claim."
            elif nli_label == "contradiction":
                verdict = "refuted"
                reason = "Source span contradicts the stated claim."
            else:
                verdict = "unverified"
                reason = f"Insufficient entailment ({nli_label}, confidence={nli_conf})."

        with self.db._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO citations(
                       citation_id, tenant_id, workspace_id, claim_text,
                       source_path, quoted_span, source_hash, span_verified,
                       nli_label, nli_confidence, verdict, checked_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    citation_id,
                    ctx.tenant_id,
                    ctx.workspace_id,
                    claim_text,
                    source_path,
                    quoted_span,
                    source_hash,
                    1 if span_ok else 0,
                    nli_label,
                    nli_conf,
                    verdict,
                    time.time(),
                ),
            )

        return VerificationResult(
            citation_id=citation_id,
            verdict=verdict,
            span_verified=span_ok,
            nli_label=nli_label,
            nli_confidence=nli_conf,
            source_hash=source_hash,
            reason=reason,
        )
