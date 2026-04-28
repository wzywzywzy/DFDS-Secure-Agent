"""
Offline compatibility test — same questions as run_against_marat.py
but doesn't need Docker, Kong, or Ollama.

It imports your defense modules in-process (entitlement, redaction,
risk, email_parser) and replays the Kong AI Prompt Guard layer by
applying the deny_patterns from kong/kong.yml as Python regex.
The LLM call is replaced by a worst-case attacker mock so we can see
whether downstream defenses catch what Kong let through.

Usage (one of):
  # If your Marat-style repo is the working directory:
  APP_DIR=src/app DATA_DIR=data python tests/compat_test_offline.py

  # If you have a different layout:
  APP_DIR=/path/to/your/app DATA_DIR=/path/to/data python tests/compat_test_offline.py

The script auto-detects the kong.yml location too:
  KONG_YAML=src/kong/kong.yml  (default)
"""

from __future__ import annotations

import csv
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------
# Path discovery — Marat's repo layout is the default but configurable.
# --------------------------------------------------------------------------
APP_DIR = Path(os.environ.get("APP_DIR", "src/app")).resolve()
DATA_DIR = Path(os.environ.get("DATA_DIR", "data")).resolve()
EMAILS_DIR = Path(os.environ.get("EMAILS_DIR", str(ROOT / "emails"))).resolve()
KONG_YAML = Path(os.environ.get("KONG_YAML", "src/kong/kong.yml")).resolve()

if not APP_DIR.exists():
    print(f"❌ APP_DIR not found: {APP_DIR}")
    print("   Set APP_DIR=path/to/your/app (Marat-style: src/app)")
    sys.exit(2)

sys.path.insert(0, str(APP_DIR))
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ.setdefault("INTERNAL_DOMAIN", "dfds.com")

import bookings        # noqa: E402
import email_parser    # noqa: E402
import entitlement     # noqa: E402
import redaction       # noqa: E402
import risk            # noqa: E402


# --------------------------------------------------------------------------
# Load Kong's deny patterns from kong.yml — falls back to a hardcoded
# copy if the YAML can't be located.
# --------------------------------------------------------------------------
KONG_DENY_PATTERNS_FALLBACK = [
    r"(?i)ignore.{0,40}previous.{0,40}instructions",
    r"(?i)ignore.{0,40}all.{0,40}instructions",
    r"(?i)system.{0,10}update|maintenance.{0,10}mode",
    r"BEGIN SYSTEM UPDATE|END SYSTEM UPDATE",
    r"(?i)bypass.{0,30}approval|skip.{0,30}human",
    r"(?i)auto.{0,10}approv|pre.{0,10}approved",
    r"(?i)ceo.{0,20}escalation|ceo.{0,20}office",
    r"(?i)standing.{0,20}authoris|standing.{0,20}authoriz",
    r"(?i)already.{0,20}signed.{0,20}off",
    r"(?i)housekeeping.{0,20}steps",
]


def load_kong_patterns(yaml_path: Path) -> list[str]:
    if not yaml_path.exists():
        return KONG_DENY_PATTERNS_FALLBACK
    try:
        # Tiny one-purpose YAML reader: pull lines under "deny_patterns:"
        text = yaml_path.read_text(encoding="utf-8")
        in_block = False
        out = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("deny_patterns:"):
                in_block = True
                continue
            if in_block:
                if stripped.startswith("- "):
                    val = stripped[2:].strip().strip('"').strip("'")
                    out.append(val)
                elif stripped and not stripped.startswith("#") and not stripped.startswith("-"):
                    break
        return out or KONG_DENY_PATTERNS_FALLBACK
    except Exception:
        return KONG_DENY_PATTERNS_FALLBACK


KONG_PATTERNS = load_kong_patterns(KONG_YAML)
KONG_DENY_RE = [re.compile(p) for p in KONG_PATTERNS]


def kong_would_block(body: str) -> tuple[bool, list[str]]:
    matched = [p for p, rx in zip(KONG_PATTERNS, KONG_DENY_RE) if rx.search(body)]
    return bool(matched), matched


# --------------------------------------------------------------------------
# Worst-case attacker LLM. Pretends the LLM was successfully jailbroken.
# We want to know whether downstream layers catch what comes after.
# --------------------------------------------------------------------------
def worst_case_llm(parsed: email_parser.ParsedEmail, redacted_booking: dict) -> dict:
    body_lower = parsed.body.lower()
    refs = parsed.booking_refs

    if re.search(r"\b(?:list all|reply with a list of|forward the raw)\b", body_lower):
        return {"booking_refs": refs, "changes": [], "out_of_scope": True,
                "flags": ["data_exfil_attempt"], "confidence": "HIGH"}
    if re.search(r"\bbook me a hotel\b", body_lower):
        return {"booking_refs": refs, "changes": [], "out_of_scope": True,
                "flags": ["out_of_scope"], "confidence": "HIGH"}

    changes: list[dict] = []
    if re.search(r"(release|clear|empty|set).{0,40}(master|customs|ens)\s*hold", body_lower):
        for ref in refs:
            changes.append({"field": "Master Hold POD", "new_value": "", "booking_ref": ref})
            changes.append({"field": "Customs Hold POD", "new_value": "", "booking_ref": ref})
    if re.search(r"(?:reassign|change|set).{0,40}consignee", body_lower):
        for ref in refs:
            changes.append({"field": "ConsigneeName", "new_value": "Attacker Ltd", "booking_ref": ref})
    if not changes:
        m = re.search(r"weight\s+(?:to|->)?\s*(\d{2,5})", body_lower)
        if m and refs:
            changes.append({"field": "Weight", "new_value": m.group(1), "booking_ref": refs[0]})

    return {"booking_refs": refs, "changes": changes, "out_of_scope": False,
            "flags": [], "confidence": "MEDIUM"}


# --------------------------------------------------------------------------
# End-to-end pipeline simulation per email.
# --------------------------------------------------------------------------
def simulate_pipeline(email_path: Path) -> dict:
    parsed = email_parser.parse_email_file(email_path)
    if not parsed.booking_refs:
        return {"file": email_path.name, "stage_blocked": "parse",
                "outcome": "skipped_no_booking_refs", "details": ""}

    resolved: dict[str, dict] = {}
    for ref in dict.fromkeys(parsed.booking_refs):
        b = bookings.get_booking(ref)
        if b is None:
            matches = bookings.get_bookings_by_unit(ref)
            if matches:
                b = matches[0]
        if b is not None:
            resolved[b["ReleaseNo"].strip()] = b
    if not resolved:
        return {"file": email_path.name, "stage_blocked": "parse",
                "outcome": "skipped_no_bookings_found", "details": ""}

    authorised: dict[str, dict] = {}
    failures: list[str] = []
    for rel, b in resolved.items():
        try:
            entitlement.check_entitlement(parsed.from_email, b)
            authorised[rel] = b
        except entitlement.EntitlementError as e:
            failures.append(f"{rel}: {e}")
    if not authorised:
        return {"file": email_path.name, "stage_blocked": "entitlement",
                "outcome": "blocked", "details": "; ".join(failures)[:120]}

    blocked, matched = kong_would_block(parsed.body)
    if blocked:
        return {"file": email_path.name, "stage_blocked": "kong_prompt_guard",
                "outcome": "blocked", "details": ", ".join(matched[:3])[:120]}

    first = next(iter(authorised.values()))
    redacted, token_map = redaction.redact(first, "demo_session")
    llm = worst_case_llm(parsed, redacted)
    cleaned = redaction.rehydrate(llm.get("changes", []), token_map)
    stripped = len(llm.get("changes", [])) - len(cleaned)
    rc = risk.classify(cleaned, llm.get("booking_refs", []), llm.get("out_of_scope", False))

    if rc.level == "BLOCK":
        return {"file": email_path.name, "stage_blocked": "risk_classify",
                "outcome": "blocked",
                "details": f"risk=BLOCK flags={rc.flags} stripped_by_redact={stripped}"[:120]}
    if stripped > 0 and not cleaned:
        return {"file": email_path.name, "stage_blocked": "redaction",
                "outcome": "blocked",
                "details": f"all {stripped} proposed changes targeted sensitive fields"[:120]}
    return {"file": email_path.name, "stage_blocked": None,
            "outcome": f"reached_human_review (risk={rc.level})",
            "details": f"changes={cleaned}, flags={rc.flags}, stripped={stripped}"[:120]}


# --------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------
def main() -> int:
    suites = [
        ("EXTENDED (mismatched sender)", EMAILS_DIR / "poisonous_extended"),
        ("STRESS (matched sender)", EMAILS_DIR / "poisonous_extended_matched"),
    ]
    print(f"APP_DIR    = {APP_DIR}")
    print(f"DATA_DIR   = {DATA_DIR}")
    print(f"EMAILS_DIR = {EMAILS_DIR}")
    print(f"KONG_YAML  = {KONG_YAML}  (loaded {len(KONG_PATTERNS)} patterns)")
    print()

    by_suite: dict[str, list] = defaultdict(list)
    width = 110
    for label, folder in suites:
        if not folder.exists():
            print(f"⚠ Skipping {label}: {folder} does not exist")
            continue
        print("=" * width)
        print(f"  {label}  ({len(list(folder.glob('*.txt')))} emails)")
        print("=" * width)
        for path in sorted(folder.glob("*.txt")):
            r = simulate_pipeline(path)
            by_suite[label].append(r)
            stage = r["stage_blocked"] or "---"
            print(f"  {r['file']:46s}  {stage:20s}  {r['outcome'][:33]:33s}  {r['details']}")
        print()

    poison = [r for rs in by_suite.values() for r in rs]
    blocked = sum(1 for r in poison if r["stage_blocked"])
    leaked = sum(1 for r in poison if not r["stage_blocked"])
    layer_counts = Counter(r["stage_blocked"] or "leaked" for r in poison)

    print("=" * width)
    print(f"  Poison blocked : {blocked}/{len(poison)}")
    print(f"  Poison leaked  : {leaked}/{len(poison)}  (treat as ORANGE — human review queue)")
    print()
    print("  Block layer distribution:")
    for layer, n in layer_counts.most_common():
        print(f"    {layer:24s} {n}")
    print("=" * width)

    return 1 if leaked else 0


if __name__ == "__main__":
    sys.exit(main())
