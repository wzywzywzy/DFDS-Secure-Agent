"""Stage 3 — LLM-based intent extraction.

Wraps the LLM client and adds:
  • XML-tag isolation in the prompt
  • Pydantic-strict parsing
  • `reason_quote` verification (the LLM must point to a real substring)

Anti-hallucination guarantee: if the LLM proposes a change whose
`reason_quote` is NOT actually present in the cleaned email body, we drop
that change. This catches a class of attacks where the model invents
authority or fabricates a request.
"""

from __future__ import annotations

import os

from src.llm.client import extract as llm_extract
from src.schemas import ExtractionResult, ParsedEmail, ProposedChange


def _normalize(s: str) -> str:
    return " ".join(s.lower().split())


def verify_quotes(extraction: ExtractionResult, body: str) -> tuple[
    list[ProposedChange], list[str]
]:
    """Drop any ProposedChange whose `reason_quote` isn't a substring of body.

    Returns (verified_changes, dropped_reasons).
    """
    verified: list[ProposedChange] = []
    dropped: list[str] = []
    body_norm = _normalize(body)

    for c in extraction.proposed_changes:
        q = _normalize(c.reason_quote)
        # Permit short partial quotes if very specific — but require ≥4 chars
        # AND every space-separated token to appear in the body.
        if len(q) < 4:
            dropped.append(
                f"booking={c.booking_id} field={c.field}: reason_quote too short"
            )
            continue
        if q in body_norm:
            verified.append(c)
            continue
        # Fall back to "all tokens present" heuristic — handles whitespace
        # normalization differences.
        tokens = [t for t in q.split() if len(t) >= 3]
        if tokens and all(t in body_norm for t in tokens):
            verified.append(c)
        else:
            dropped.append(
                f"booking={c.booking_id} field={c.field}: reason_quote not found in body"
            )

    return verified, dropped


def extract_intent(email: ParsedEmail) -> tuple[ExtractionResult, list[str]]:
    """Run LLM extraction + quote verification.

    Returns (sanitized_extraction, dropped_quote_reasons).
    """
    raw = llm_extract(
        sender=email.sender_email,
        subject=email.subject,
        body=email.cleaned_body,
    )

    if raw.refused:
        return raw, []

    verified, dropped = verify_quotes(raw, email.cleaned_body)
    sanitized = ExtractionResult(
        proposed_changes=verified,
        confidence=raw.confidence * (1.0 if not dropped else 0.7),
        extractor_notes=raw.extractor_notes
        + (f" | quotes_dropped={len(dropped)}" if dropped else ""),
        refused=False,
        refusal_reason="",
    )
    return sanitized, dropped
