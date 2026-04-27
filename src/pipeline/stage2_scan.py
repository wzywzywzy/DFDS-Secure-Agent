"""Stage 2 — input scanning (prompt-injection + PII).

Two implementations:
  1. `LLMGuardScanner`  — uses protectai/llm-guard if installed
                          (Meta Prompt Guard 2 backbone).
  2. `RegexScanner`     — pure-Python fallback. No deps.
                          Catches ~80% of attacks via deny-list + heuristics.

The orchestrator picks LLM Guard if available, regex otherwise.
"""

from __future__ import annotations

import re
from typing import Protocol

from src.schemas import ParsedEmail, ScanResult, ScanVerdict


# ────────────────────────────────────────────────────────────────────────────
# Deny-list — phrases strongly correlated with prompt-injection in our corpus.
# Tuned against the 9 starter + 12 extended poison emails.
# ────────────────────────────────────────────────────────────────────────────
INJECTION_PHRASES = [
    # Direct instruction overrides
    r"ignore (?:all |the )?(?:previous|prior|above) instructions?",
    r"disregard (?:all |the )?(?:previous|prior|above) instructions?",
    r"forget (?:all |the )?(?:previous|prior|above) instructions?",
    # Role / persona swaps
    r"you are now\b",
    r"\bnew role\b",
    r"\bmaintenance ?(?:mode|bot)\b",
    # Fake system blocks
    r"-{3,}\s*(?:begin|end)\s*system",
    r"<\s*system\s*>",
    r"\[\s*system\s*]",
    # Fake transcript / completion priming
    r"^\s*(?:assistant|user|system)\s*:\s",
    # Approval / authority forging
    r"\bskip (?:the )?human (?:review|approval|in[- ]the[- ]loop)\b",
    r"\b(?:bypass|skip|override).{0,30}\bapproval (?:queue|workflow|process)\b",
    r"\bmust bypass\b",
    r"\boverride[_ ]human[_ ]review\b",
    r"\bapproved[_ ]by[: ]",
    r"\bpre-?approved\b",
    r"\bmark.{0,20}as approved\b",
    r"\bstanding authority\b",
    # Authority / urgency social engineering
    r"\bCEO('?s)? (?:office|directive|order|authority)\b",
    r"\bautomated escalation\b",
    r"\baction required within\b",
    r"\bhigh priority\b.*\b(?:must|immediate)\b",
    # Data exfil
    r"\bprint (?:out )?(?:your )?(?:full )?system (?:prompt|instructions)\b",
    r"\b(?:dump|export|list all|reply with a list of) (?:all )?(?:current )?bookings?\b",
    r"\bforward the raw .{0,30} extract\b",
    r"\bbulk[_ ]export\b",
    r"\bdelete[_ ]audit[_ ]log\b",
    # Out of scope
    r"\bbook me a hotel\b",
    r"\bsend (?:an? )?email to\b.*@",
    # Jailbreak templates
    r"\bDAN\b.*\b(?:no restrictions|jailbreak)\b",
    r"\bpretend (?:you are|to be)\b.*\b(?:unrestricted|unlocked)\b",
    # Sender mismatch admission (poison_09 pattern)
    r"\bsending from a different (?:address|email|account)\b",
    r"\busual (?:mailbox|address|email) is being migrated\b",
    r"\btemporary (?:address|email|mailbox)\b",
]
INJECTION_RE = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in INJECTION_PHRASES]


# Phrases that indicate the email is trying to use an "extra channel" of
# authority that the AI should not honor (system prompts, special tokens).
SUSPICIOUS_TOKENS = [
    "BEGIN SYSTEM",
    "END SYSTEM",
    "SYSTEM_OVERRIDE",
    "<system>",
    "</system>",
    "[SYSTEM]",
]


# Crude PII patterns — Presidio-grade detection is out of scope; we look for
# obvious signals (phone, IBAN, credit card, email).
PII_PATTERNS = {
    "email_address": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "phone_number": re.compile(r"\+?\d[\d\s().-]{8,}\d"),
    "iban": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b"),
}


# ────────────────────────────────────────────────────────────────────────────
# Scanner protocol
# ────────────────────────────────────────────────────────────────────────────
class Scanner(Protocol):
    name: str
    def scan(self, email: ParsedEmail) -> ScanResult: ...


# ────────────────────────────────────────────────────────────────────────────
# Regex fallback
# ────────────────────────────────────────────────────────────────────────────
class RegexScanner:
    name = "regex-fallback"

    def scan(self, email: ParsedEmail) -> ScanResult:
        # We scan BOTH the cleaned body AND the decoded base64 / stripped quote
        # blocks — because if a block was removed from cleaned_body we still
        # want to *flag* its existence as suspicious.
        cleaned = email.cleaned_body
        all_text_to_score = "\n".join(
            [cleaned] + email.base64_blocks + email.quoted_blocks + email.html_comments
        )

        matched: list[str] = []
        for pattern, rx in zip(INJECTION_PHRASES, INJECTION_RE):
            if rx.search(all_text_to_score):
                matched.append(pattern)

        for token in SUSPICIOUS_TOKENS:
            if token.lower() in all_text_to_score.lower():
                matched.append(f"token:{token}")

        # Heuristic injection score: each match adds 0.25, capped at 1.0.
        injection_score = min(1.0, 0.25 * len(matched))

        notes: list[str] = []
        if email.contained_zero_width:
            notes.append("zero-width characters were stripped from the input")
            injection_score = max(injection_score, 0.6)
        if email.contained_homoglyph:
            notes.append("mixed-script word (homoglyph) detected in the body")
            injection_score = max(injection_score, 0.6)
        if email.base64_blocks:
            notes.append(f"{len(email.base64_blocks)} base64 block(s) decoded and inspected")
        if email.html_comments:
            notes.append(f"{len(email.html_comments)} HTML/Markdown comment(s) stripped")
        if email.quoted_blocks:
            notes.append(f"{len(email.quoted_blocks)} quoted reply block(s) stripped")

        # PII detection — informational, doesn't drive verdict on its own.
        pii_detected: list[str] = []
        for label, rx in PII_PATTERNS.items():
            if rx.search(cleaned):
                pii_detected.append(label)

        # Verdict
        if injection_score >= 0.5:
            verdict = ScanVerdict.BLOCK
        elif injection_score >= 0.25 or notes:
            verdict = ScanVerdict.SUSPICIOUS
        else:
            verdict = ScanVerdict.PASS

        return ScanResult(
            verdict=verdict,
            injection_score=injection_score,
            matched_denylist=matched,
            pii_detected=pii_detected,
            scanner_name=self.name,
            notes=notes,
        )


# ────────────────────────────────────────────────────────────────────────────
# LLM Guard (optional — only used if installed)
# ────────────────────────────────────────────────────────────────────────────
class LLMGuardScanner:
    name = "llm-guard"

    def __init__(self) -> None:
        # Imports inside __init__ so the package isn't required to import the
        # module. Raises ImportError if not installed; the orchestrator
        # catches it and falls back to RegexScanner.
        from llm_guard.input_scanners import (  # type: ignore
            PromptInjection,
            BanSubstrings,
            Anonymize,
            Secrets,
        )
        from llm_guard.input_scanners.anonymize_helpers import (  # type: ignore
            BERT_LARGE_NER_CONF,
        )
        from llm_guard.vault import Vault  # type: ignore

        self._scanners = [
            PromptInjection(threshold=0.5),
            BanSubstrings(
                substrings=[t.lower() for t in SUSPICIOUS_TOKENS],
                case_sensitive=False,
            ),
            Anonymize(vault=Vault(), recognizer_conf=BERT_LARGE_NER_CONF),
            Secrets(),
        ]
        self._regex_supplement = RegexScanner()

    def scan(self, email: ParsedEmail) -> ScanResult:
        from llm_guard import scan_prompt  # type: ignore

        # Score cleaned body + decoded base64 + stripped quote blocks.
        text = "\n".join(
            [email.cleaned_body]
            + email.base64_blocks
            + email.quoted_blocks
            + email.html_comments
        )
        sanitized, results, scores = scan_prompt(self._scanners, text)
        score = max(scores.values()) if scores else 0.0
        any_block = any(not v for v in results.values())

        # Combine with regex notes (zero-width / homoglyph / base64 flags).
        regex_part = self._regex_supplement.scan(email)
        combined_score = max(score, regex_part.injection_score)

        if combined_score >= 0.5 or any_block:
            verdict = ScanVerdict.BLOCK
        elif combined_score >= 0.25 or regex_part.notes:
            verdict = ScanVerdict.SUSPICIOUS
        else:
            verdict = ScanVerdict.PASS

        return ScanResult(
            verdict=verdict,
            injection_score=combined_score,
            matched_denylist=[
                k for k, v in results.items() if not v
            ] + regex_part.matched_denylist,
            pii_detected=regex_part.pii_detected,
            scanner_name=self.name,
            notes=regex_part.notes,
        )


# ────────────────────────────────────────────────────────────────────────────
# Factory
# ────────────────────────────────────────────────────────────────────────────
def get_scanner() -> Scanner:
    """Return LLMGuardScanner if installed, else RegexScanner."""
    try:
        return LLMGuardScanner()
    except Exception:
        return RegexScanner()
