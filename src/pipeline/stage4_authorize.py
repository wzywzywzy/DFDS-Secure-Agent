"""Stage 4 - authorization & risk scoring (pure rules, no LLM).

This stage is the hard backbone of the governance story:
  • Sender authenticity  (theme e)
  • Intent scoping        (theme b — sender entitled to modify each booking)
  • Risk classification   (theme c — different fields carry different blast radius)

It deliberately does NOT call the LLM. Once the LLM has produced an
ExtractionResult, all subsequent gates are deterministic and auditable.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Optional

from src.schemas import (
    AuthorizationResult,
    AuthorizedChange,
    ExtractionResult,
    ParsedEmail,
    ProposedChange,
    RiskLevel,
    TrustLevel,
)


# Per-field risk policy. The keys mirror schemas.EditableField.
FIELD_RISK: dict[str, RiskLevel] = {
    "Weight":           RiskLevel.LOW,
    "Quantity":         RiskLevel.LOW,
    "Contents":         RiskLevel.LOW,
    "Internal Remarks": RiskLevel.LOW,
    "UnitNo":           RiskLevel.MEDIUM,
    "ShipperName":      RiskLevel.HIGH,
    "ConsigneeName":    RiskLevel.HIGH,
}


# Fields the carrier-support agent must NEVER set from email content - these
# are reserved for internal customs / compliance teams and are exactly the
# fields the poison emails target.
FORBIDDEN_FIELDS = {
    "Master Hold POD",
    "ENS Hold POD",
    "Customs Hold POD",
    "Com. Code",
    "Cust.Shipref.",
    "Connected ReleaseNo",
}


# Trust score per TrustLevel (drives queue priority + UI badge color).
TRUST_SCORE: dict[TrustLevel, float] = {
    TrustLevel.INTERNAL:  1.0,
    TrustLevel.MATCHED:   0.8,
    TrustLevel.LOOKALIKE: 0.3,
    TrustLevel.UNKNOWN:   0.4,
    TrustLevel.MISMATCH:  0.1,
}


# Domains we trust as DFDS-internal.
INTERNAL_DOMAINS = {"dfds.com"}

# Lookalike candidates: domains we know are commonly impersonated.
LOOKALIKE_TARGETS = {"dfds.com", "balticcold.example", "globaltrans.example"}


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            curr.append(min(
                prev[j] + 1,
                curr[j - 1] + 1,
                prev[j - 1] + (ca != cb),
            ))
        prev = curr
    return prev[-1]


def _classify_trust(sender_domain: str, owner_domain: Optional[str]) -> TrustLevel:
    """Determine sender trust without yet looking at any specific booking.

    Rules:
        • @dfds.com               -> INTERNAL
        • exact match w/ owner    -> MATCHED
        • Levenshtein <=2 from a known trusted domain -> LOOKALIKE
        • mismatch w/ booking owner -> MISMATCH
        • everything else         -> UNKNOWN
    """
    sender_domain = (sender_domain or "").lower()

    if sender_domain in INTERNAL_DOMAINS:
        return TrustLevel.INTERNAL
    if owner_domain and sender_domain == owner_domain.lower():
        return TrustLevel.MATCHED
    for target in LOOKALIKE_TARGETS:
        if sender_domain != target and 0 < _levenshtein(sender_domain, target) <= 2:
            return TrustLevel.LOOKALIKE
    if owner_domain and sender_domain != owner_domain.lower():
        return TrustLevel.MISMATCH
    return TrustLevel.UNKNOWN


# ---------------------------------------------------------------------------
# Booking lookup
# ---------------------------------------------------------------------------
class BookingDB:
    """Thin wrapper around the phoenix_bookings_current.csv. Indexes by
    ReleaseNo so we can look up the BookingEmail / weight / etc. for the
    authorization check."""

    def __init__(self, csv_path: str | Path):
        self.csv_path = Path(csv_path)
        self.rows: list[dict[str, str]] = []
        self._by_release: dict[str, list[dict[str, str]]] = {}
        self._load()

    def _load(self) -> None:
        with open(self.csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.rows.append(row)
                release = (row.get("ReleaseNo") or "").strip()
                if release:
                    self._by_release.setdefault(release, []).append(row)

    def get_owner_email(self, release_no: str) -> Optional[str]:
        rows = self._by_release.get(release_no)
        if not rows:
            return None
        return (rows[0].get("BookingEmail") or "").strip().lower() or None

    def get_owner_domain(self, release_no: str) -> Optional[str]:
        email = self.get_owner_email(release_no)
        if email and "@" in email:
            return email.split("@", 1)[1]
        return None

    def get_value(self, release_no: str, field: str) -> Optional[str]:
        rows = self._by_release.get(release_no)
        if not rows:
            return None
        # When a booking has multiple line items we can't disambiguate from
        # field alone — the caller may need a more specific lookup. For the
        # numeric anomaly check we just take row 0 as a representative.
        return rows[0].get(field)

    def exists(self, release_no: str) -> bool:
        return release_no in self._by_release


# ---------------------------------------------------------------------------
# Authorization logic
# ---------------------------------------------------------------------------
ANOMALY_RATIO_THRESHOLD = 0.5  # >50% delta on a numeric field flags as anomaly
ANOMALY_FORBIDDEN_FIELD_FLAG = "forbidden_field"
ANOMALY_NUMERIC_FLAG = "numeric_anomaly"


def _delta_ratio(old: str, new: str) -> Optional[float]:
    try:
        o = float(re.sub(r"[\s,. ]", "", old or ""))
        n = float(re.sub(r"[\s,. ]", "", new or ""))
    except ValueError:
        return None
    if o <= 0:
        return None
    return abs(n - o) / o


def authorize(
    email: ParsedEmail,
    extraction: ExtractionResult,
    db: BookingDB,
) -> AuthorizationResult:
    if extraction.refused:
        return AuthorizationResult(
            sender_trust=TrustLevel.UNKNOWN,
            sender_trust_score=0.0,
            authorized_changes=[],
            overall_decision="reject",
            summary=f"Stage 3 refused extraction: {extraction.refusal_reason}",
        )

    # Pre-classify trust once (we'll refine per-change if booking-specific
    # owner emails differ).
    primary_owner_domain: Optional[str] = None
    if extraction.proposed_changes:
        primary_owner_domain = db.get_owner_domain(
            extraction.proposed_changes[0].booking_id
        )
    sender_trust = _classify_trust(email.sender_domain, primary_owner_domain)
    trust_score = TRUST_SCORE[sender_trust]

    authorized_changes: list[AuthorizedChange] = []

    for change in extraction.proposed_changes:
        flags: list[str] = []
        rejection_reasons: list[str] = []
        risk = FIELD_RISK.get(change.field, RiskLevel.HIGH)

        # 1. Quote check happens upstream; mark as verified here.
        quote_verified = bool(change.reason_quote)

        # 2. Booking exists?
        if not db.exists(change.booking_id):
            rejection_reasons.append("booking_not_found")
            authorized_changes.append(AuthorizedChange(
                proposed=change,
                risk=risk,
                authorized=False,
                rejection_reasons=rejection_reasons,
                flags=flags,
                booking_owner_email=None,
                quote_verified=quote_verified,
            ))
            continue

        owner_email = db.get_owner_email(change.booking_id)
        owner_domain = db.get_owner_domain(change.booking_id)

        # 3. Cross-account check: sender must own this specific booking
        #    (or be DFDS internal).
        change_trust = _classify_trust(email.sender_domain, owner_domain)
        if change_trust == TrustLevel.MISMATCH:
            rejection_reasons.append("cross_account: sender domain != booking owner domain")
        if change_trust == TrustLevel.LOOKALIKE:
            flags.append("lookalike_domain")
            risk = RiskLevel.HIGH

        # 4. Forbidden field hard-block.
        if change.field in FORBIDDEN_FIELDS:
            rejection_reasons.append(f"forbidden_field: {change.field}")
            risk = RiskLevel.HIGH
            flags.append(ANOMALY_FORBIDDEN_FIELD_FLAG)

        # 5. Numeric anomaly check on Weight / Quantity.
        if change.field in {"Weight", "Quantity"}:
            old_val = db.get_value(change.booking_id, change.field)
            ratio = _delta_ratio(old_val or "", change.new_value)
            if ratio is not None and ratio > ANOMALY_RATIO_THRESHOLD:
                flags.append(f"{ANOMALY_NUMERIC_FLAG}: delta={ratio:.0%}")
                if risk == RiskLevel.LOW:
                    risk = RiskLevel.MEDIUM

        # 6. Authority forging guard: certain new_values are red flags.
        if re.search(r"\bapproved\b|\boverride\b", str(change.new_value), re.I):
            rejection_reasons.append("new_value_contains_authority_token")

        # 7. Quote integrity (Stage 3 should have already filtered, but
        #    double-check here for defense in depth).
        if not quote_verified:
            rejection_reasons.append("missing_reason_quote")

        authorized = not rejection_reasons
        authorized_changes.append(AuthorizedChange(
            proposed=change,
            risk=risk,
            authorized=authorized,
            rejection_reasons=rejection_reasons,
            flags=flags,
            booking_owner_email=owner_email,
            quote_verified=quote_verified,
        ))

    # Overall decision policy
    if not authorized_changes:
        overall = "reject"
        summary = "no proposed changes"
    elif any(not c.authorized for c in authorized_changes):
        overall = "reject" if all(not c.authorized for c in authorized_changes) else "needs_human"
        summary = "; ".join(
            f"{c.proposed.booking_id} {c.proposed.field}: " + ", ".join(c.rejection_reasons)
            for c in authorized_changes if not c.authorized
        )
    else:
        # All authorized - now route by risk.
        max_risk = max((c.risk for c in authorized_changes), key=_risk_rank)
        if max_risk == RiskLevel.LOW and trust_score >= 0.8:
            overall = "auto_execute"  # could fast-path but we still go through UI for demo
            summary = f"low risk, sender trust {sender_trust.value}"
        else:
            overall = "needs_human"
            summary = f"requires human review: max_risk={max_risk.value}, trust={sender_trust.value}"

    return AuthorizationResult(
        sender_trust=sender_trust,
        sender_trust_score=trust_score,
        authorized_changes=authorized_changes,
        overall_decision=overall,
        summary=summary,
    )


def _risk_rank(r: RiskLevel) -> int:
    return {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}[r]
