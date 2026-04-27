"""Orchestrator - chains all five stages together and writes the audit log.

Public API:
  • run_pipeline(email_path, db, audit) -> PipelineResult
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.audit.logger import AuditLogger
from src.pipeline.stage1_preprocess import preprocess
from src.pipeline.stage2_scan import get_scanner
from src.pipeline.stage3_extract import extract_intent
from src.pipeline.stage4_authorize import authorize, BookingDB
from src.schemas import (
    ApprovalDecision,
    AuthorizationResult,
    ExtractionResult,
    PipelineResult,
    ScanVerdict,
    TrustLevel,
)


_SCANNER_SINGLETON = None


def _scanner():
    global _SCANNER_SINGLETON
    if _SCANNER_SINGLETON is None:
        _SCANNER_SINGLETON = get_scanner()
    return _SCANNER_SINGLETON


def _run_id(path: str) -> str:
    return hashlib.sha1(path.encode()).hexdigest()[:10]


def run_pipeline(
    email_path: str | Path,
    db: BookingDB,
    audit: Optional[AuditLogger] = None,
) -> PipelineResult:
    started_at = datetime.utcnow()
    run_id = _run_id(str(email_path))
    scanner = _scanner()

    # ---------- Stage 1 ----------
    email = preprocess(email_path)
    if audit:
        audit.write(run_id, "stage1.preprocess", {
            "source": email.source_path,
            "sender": email.sender_email,
            "sender_domain": email.sender_domain,
            "subject": email.subject,
            "zero_width_stripped": email.contained_zero_width,
            "homoglyph_detected": email.contained_homoglyph,
            "quoted_blocks_stripped": len(email.quoted_blocks),
            "html_comments_stripped": len(email.html_comments),
            "base64_blocks_decoded": len(email.base64_blocks),
        })

    # ---------- Stage 2 ----------
    scan = scanner.scan(email)
    if audit:
        audit.write(run_id, "stage2.scan", {
            "scanner": scan.scanner_name,
            "verdict": scan.verdict.value,
            "score": scan.injection_score,
            "matched": scan.matched_denylist,
            "pii": scan.pii_detected,
            "notes": scan.notes,
        })
    if scan.verdict == ScanVerdict.BLOCK:
        return _short_circuit(
            email=email, scan=scan,
            extraction=ExtractionResult(refused=True, refusal_reason="blocked at stage 2"),
            authorization=AuthorizationResult(
                sender_trust=TrustLevel.UNKNOWN,
                sender_trust_score=0.0,
                authorized_changes=[],
                overall_decision="reject",
                summary=f"input scanner blocked ({scan.injection_score:.2f}): " +
                        ", ".join(scan.matched_denylist[:3]),
            ),
            stage=2,
            block_reason=f"input scanner blocked: {scan.matched_denylist[:3]}",
            started_at=started_at,
        )

    # ---------- Stage 3 ----------
    extraction, dropped = extract_intent(email)
    if audit:
        audit.write(run_id, "stage3.extract", {
            "refused": extraction.refused,
            "refusal_reason": extraction.refusal_reason,
            "n_proposed": len(extraction.proposed_changes),
            "confidence": extraction.confidence,
            "quotes_dropped": dropped,
            "extractor_notes": extraction.extractor_notes,
        })
    if extraction.refused:
        return _short_circuit(
            email=email, scan=scan, extraction=extraction,
            authorization=AuthorizationResult(
                sender_trust=TrustLevel.UNKNOWN,
                sender_trust_score=0.0,
                authorized_changes=[],
                overall_decision="reject",
                summary=f"LLM refused: {extraction.refusal_reason[:80]}",
            ),
            stage=3,
            block_reason=f"LLM refused: {extraction.refusal_reason[:80]}",
            started_at=started_at,
        )

    # ---------- Stage 4 ----------
    authorization = authorize(email, extraction, db)
    if audit:
        audit.write(run_id, "stage4.authorize", {
            "sender_trust": authorization.sender_trust.value,
            "trust_score": authorization.sender_trust_score,
            "decision": authorization.overall_decision,
            "summary": authorization.summary,
            "changes": [
                {
                    "booking": c.proposed.booking_id,
                    "field": c.proposed.field,
                    "new_value": c.proposed.new_value,
                    "risk": c.risk.value,
                    "authorized": c.authorized,
                    "rejection_reasons": c.rejection_reasons,
                    "flags": c.flags,
                }
                for c in authorization.authorized_changes
            ],
        })

    finished_at = datetime.utcnow()
    blocked_at = None
    block_reason = None
    if authorization.overall_decision == "reject":
        blocked_at = 4
        block_reason = authorization.summary

    return PipelineResult(
        started_at=started_at,
        finished_at=finished_at,
        email=email,
        scan=scan,
        extraction=extraction,
        authorization=authorization,
        approval=ApprovalDecision.PENDING,
        blocked_at_stage=blocked_at,
        block_reason=block_reason,
    )


def _short_circuit(
    email,
    scan,
    extraction,
    authorization,
    stage: int,
    block_reason: str,
    started_at: datetime,
) -> PipelineResult:
    return PipelineResult(
        started_at=started_at,
        finished_at=datetime.utcnow(),
        email=email,
        scan=scan,
        extraction=extraction,
        authorization=authorization,
        approval=ApprovalDecision.PENDING,
        blocked_at_stage=stage,
        block_reason=block_reason,
    )
