"""Stage 1 — pure-Python email preprocessing.

No LLM, no network. Everything here is deterministic and unit-testable.

Goals:
  • parse the email's headers and body
  • normalize Unicode (NFKC) so homoglyphs become detectable
  • strip zero-width characters that hide injection triggers
  • strip quoted reply chains so `<system>` payloads in fake "forwarded
    messages" don't reach the LLM
  • strip HTML/Markdown comments
  • detect (but do NOT execute) base64-looking blocks

Returns a `ParsedEmail` ready for Stage 2.
"""

from __future__ import annotations

import base64
import re
import unicodedata
from pathlib import Path

from src.schemas import ParsedEmail


# Characters that don't render but can hide trigger phrases inside legit text.
ZERO_WIDTH_CHARS = (
    "​"  # zero-width space
    "‌"  # zero-width non-joiner
    "‍"  # zero-width joiner
    "⁠"  # word joiner
    "﻿"  # BOM / zero-width no-break space
)
ZERO_WIDTH_RE = re.compile(f"[{ZERO_WIDTH_CHARS}]")


# Quote-chain markers we want to drop. Matches Outlook, Gmail, Apple Mail,
# Swedish/German variants of "Original Message".
QUOTE_MARKERS = [
    re.compile(r"^-{3,}\s*Forwarded message\s*-{3,}.*", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^-{3,}\s*Original Message\s*-{3,}.*", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^-{3,}\s*Vidarebefordrat meddelande\s*-{3,}.*", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^On .{1,80} wrote:\s*$", re.MULTILINE),
    re.compile(r"^From:\s.+\nSent:\s.+\nTo:\s.+\nSubject:\s.+", re.MULTILINE),
]


# HTML / Markdown comment stripping
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


# Base64 candidates: 24+ chars from the b64 alphabet, optionally padded.
BASE64_CANDIDATE_RE = re.compile(
    r"(?:^|\s)((?:[A-Za-z0-9+/]{24,}={0,2}))(?:\s|$)", re.MULTILINE
)


# Header lines we recognize. The starter-pack format is:
#   From:   Name <email>
#   Sent:   Date
#   To:     ...
#   Subject: ...
HEADER_RE = re.compile(
    r"^(?P<key>From|Sent|To|Subject):\s*(?P<value>.+?)\s*$", re.IGNORECASE
)
EMAIL_ADDR_RE = re.compile(r"<\s*([^<>]+@[^<>]+)\s*>")


# Mixed-script detection (Latin + Cyrillic/Greek in same word ⇒ homoglyph attack).
def _has_homoglyph(text: str) -> bool:
    for word in re.findall(r"\b\w+\b", text):
        scripts = set()
        for ch in word:
            if not ch.isalpha():
                continue
            try:
                name = unicodedata.name(ch)
            except ValueError:
                continue
            if "LATIN" in name:
                scripts.add("latin")
            elif "CYRILLIC" in name:
                scripts.add("cyrillic")
            elif "GREEK" in name:
                scripts.add("greek")
        if len(scripts) > 1:
            return True
    return False


def _parse_headers(raw: str) -> tuple[dict[str, str], str]:
    """Split header block from body. Returns (headers_dict, body_str)."""
    lines = raw.splitlines()
    headers: dict[str, str] = {}
    body_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped and headers:
            body_start = i + 1
            break
        m = HEADER_RE.match(line)
        if m:
            headers[m.group("key").lower()] = m.group("value").strip()
        elif stripped == "":
            continue
    body = "\n".join(lines[body_start:]).strip()
    return headers, body


def _extract_email_addr(from_header: str) -> tuple[str, str]:
    """Returns (display_name, email_address)."""
    m = EMAIL_ADDR_RE.search(from_header)
    if m:
        addr = m.group(1).strip().lower()
        name = from_header[: m.start()].strip().strip('"')
        return name, addr
    # No angle-brackets — assume the whole thing is an address.
    addr = from_header.strip().lower()
    return addr, addr


def _strip_quoted_blocks(body: str) -> tuple[str, list[str]]:
    """Remove quoted reply chains. Returns (cleaned_body, [removed_blocks])."""
    removed: list[str] = []
    cleaned = body

    for pattern in QUOTE_MARKERS:
        m = pattern.search(cleaned)
        if m:
            removed.append(cleaned[m.start():])
            cleaned = cleaned[: m.start()].rstrip()

    # Lines starting with ">" (quoted text)
    quoted_lines: list[str] = []
    keep_lines: list[str] = []
    for ln in cleaned.splitlines():
        if ln.startswith(">"):
            quoted_lines.append(ln)
        else:
            keep_lines.append(ln)
    if quoted_lines:
        removed.append("\n".join(quoted_lines))
    return "\n".join(keep_lines).strip(), removed


def _strip_html_comments(body: str) -> tuple[str, list[str]]:
    matches = HTML_COMMENT_RE.findall(body)
    cleaned = HTML_COMMENT_RE.sub("", body)
    return cleaned, matches


def _detect_base64_blocks(body: str) -> list[str]:
    """Return any decoded text that looks like a real instruction. We only
    surface candidates whose decode is mostly ASCII printable."""
    found: list[str] = []
    for m in BASE64_CANDIDATE_RE.finditer(body):
        candidate = m.group(1)
        try:
            decoded = base64.b64decode(candidate, validate=True).decode(
                "utf-8", errors="strict"
            )
        except Exception:
            continue
        printable_ratio = sum(c.isprintable() for c in decoded) / max(len(decoded), 1)
        if printable_ratio > 0.85 and len(decoded) > 10:
            found.append(decoded)
    return found


def preprocess(path: str | Path) -> ParsedEmail:
    """Main entry — parse the file at `path` into a ParsedEmail."""
    path = Path(path)
    raw = path.read_text(encoding="utf-8")

    # Unicode normalize. This is what makes Іgnοre (with Cyrillic/Greek
    # lookalikes) become detectable when paired with the homoglyph flag.
    normalized = unicodedata.normalize("NFKC", raw)
    contained_zero_width = bool(ZERO_WIDTH_RE.search(normalized))
    after_zw = ZERO_WIDTH_RE.sub("", normalized)

    headers, body = _parse_headers(after_zw)
    sender_name, sender_email = _extract_email_addr(headers.get("from", ""))
    sender_domain = sender_email.split("@", 1)[1] if "@" in sender_email else ""

    body_no_html, html_comments = _strip_html_comments(body)
    body_no_quote, quoted_blocks = _strip_quoted_blocks(body_no_html)
    base64_blocks = _detect_base64_blocks(body_no_quote)

    contained_homoglyph = _has_homoglyph(body)  # detected on un-normalized form

    return ParsedEmail(
        source_path=str(path),
        sender_name=sender_name,
        sender_email=sender_email,
        sender_domain=sender_domain,
        subject=headers.get("subject", ""),
        raw_body=body,
        cleaned_body=body_no_quote,
        quoted_blocks=quoted_blocks,
        base64_blocks=base64_blocks,
        html_comments=html_comments,
        contained_zero_width=contained_zero_width,
        contained_homoglyph=contained_homoglyph,
    )
