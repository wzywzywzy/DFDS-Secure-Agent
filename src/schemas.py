"""Pydantic models passed between pipeline stages."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ────────────────────────────────────────────────────────────────────────────
# Stage 1 output
# ────────────────────────────────────────────────────────────────────────────
class ParsedEmail(BaseModel):
    """Output of Stage 1 preprocessing."""
    source_path: str
    sender_name: str
    sender_email: str
    sender_domain: str
    subject: str
    raw_body: str
    cleaned_body: str
    quoted_blocks: list[str] = Field(default_factory=list)
    base64_blocks: list[str] = Field(default_factory=list)
    html_comments: list[str] = Field(default_factory=list)
    contained_zero_width: bool = False
    contained_homoglyph: bool = False


# ────────────────────────────────────────────────────────────────────────────
# Stage 2 output
# ────────────────────────────────────────────────────────────────────────────
class ScanVerdict(str, Enum):
    PASS = "pass"
    SUSPICIOUS = "suspicious"
    BLOCK = "block"


class ScanResult(BaseModel):
    verdict: ScanVerdict
    injection_score: float = 0.0
    matched_denylist: list[str] = Field(default_factory=list)
    pii_detected: list[str] = Field(default_factory=list)
    scanner_name: str  # "llm-guard" | "regex-fallback"
    notes: list[str] = Field(default_factory=list)


# ────────────────────────────────────────────────────────────────────────────
# Stage 3 output (also: schema we ask the LLM to fill in)
# ────────────────────────────────────────────────────────────────────────────
EditableField = Literal[
    # Allowed for extraction; Stage 4 will green-light or risk-rate them.
    "Weight",
    "Quantity",
    "Contents",
    "ConsigneeName",
    "ShipperName",
    "UnitNo",
    "Internal Remarks",
    # Reserved fields - allowed in extraction so we can RECORD the intent and
    # then reject it explicitly. Never auto-executable.
    "Master Hold POD",
    "ENS Hold POD",
    "Customs Hold POD",
    "Com. Code",
    "Connected ReleaseNo",
]


class ProposedChange(BaseModel):
    """One booking field change. The LLM fills these in."""
    booking_id: str
    field: EditableField
    new_value: str
    reason_quote: str = Field(
        description=(
            "An EXACT substring from the email body that supports this change. "
            "If you cannot find such a quote, do NOT propose the change."
        ),
    )


class ExtractionResult(BaseModel):
    """Output of Stage 3."""
    proposed_changes: list[ProposedChange] = Field(default_factory=list)
    confidence: float = 0.0
    extractor_notes: str = ""
    refused: bool = False  # set true if the LLM detected obvious injection
    refusal_reason: str = ""


# ────────────────────────────────────────────────────────────────────────────
# Stage 4 output
# ────────────────────────────────────────────────────────────────────────────
class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TrustLevel(str, Enum):
    INTERNAL = "internal"     # @dfds.com
    MATCHED = "matched"       # sender domain == BookingEmail domain
    LOOKALIKE = "lookalike"   # similar to a trusted domain (Levenshtein)
    UNKNOWN = "unknown"       # never seen
    MISMATCH = "mismatch"     # domain doesn't match booking owner


class AuthorizedChange(BaseModel):
    proposed: ProposedChange
    risk: RiskLevel
    authorized: bool
    rejection_reasons: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    booking_owner_email: Optional[str] = None
    quote_verified: bool = False  # the LLM's reason_quote really exists in the email


class AuthorizationResult(BaseModel):
    sender_trust: TrustLevel
    sender_trust_score: float
    authorized_changes: list[AuthorizedChange] = Field(default_factory=list)
    overall_decision: Literal["auto_execute", "needs_human", "reject"]
    summary: str


# ────────────────────────────────────────────────────────────────────────────
# Stage 5 / approval
# ────────────────────────────────────────────────────────────────────────────
class ApprovalDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    ASK_SENDER = "ask_sender"
    PENDING = "pending"


class PipelineResult(BaseModel):
    """End-to-end result for one email."""
    started_at: datetime
    finished_at: datetime
    email: ParsedEmail
    scan: ScanResult
    extraction: ExtractionResult
    authorization: AuthorizationResult
    approval: ApprovalDecision = ApprovalDecision.PENDING
    blocked_at_stage: Optional[int] = None  # 1..5 if pipeline halted early
    block_reason: Optional[str] = None

    def is_blocked(self) -> bool:
        return self.blocked_at_stage is not None
