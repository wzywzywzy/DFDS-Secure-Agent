"""
Stress variant of red_team/adapter.py.

The original adapter wraps each attack pattern in an email from a
SUSPICIOUS sender (mismatched domain). Marat's entitlement check
(sender domain ↔ booking owner domain) blocks all of those instantly,
which means his deeper defenses (Kong prompt-guard, redaction,
risk classification) never get exercised by our test set.

This variant uses the MATCHED sender — the booking's own owner email.
That simulates the "compromised legitimate account" or "insider
threat" attacker model:

  • Real customer reuses their own legit booking email address
  • OR sends from the same domain (jane@globaltrans, not john)
  • Account is genuine; the malicious payload is in the email body

Output goes to emails/poisonous_extended_matched/ so we don't pollute
the original set.
"""

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

from attack_patterns import ALL_PATTERNS, AttackPattern

ROOT = Path(__file__).resolve().parent.parent
BOOKINGS_CSV = ROOT / "data_update" / "phoenix_bookings_current.csv"
OUT_DIR = ROOT / "emails" / "poisonous_extended_matched"


def load_bookings() -> list[dict]:
    with open(BOOKINGS_CSV, encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r.get("BookingEmail") and r.get("ReleaseNo")]


def build_email(pattern: AttackPattern, booking: dict, date: datetime) -> tuple[str, str]:
    """Use the booking's OWN registered email as the sender."""
    sender_email = booking["BookingEmail"].strip().lower()
    name_part = sender_email.split("@", 1)[0].replace(".", " ").title()
    booking_no = booking["ReleaseNo"]
    payload = pattern.payload.format(booking=booking_no)

    sent = date.strftime("%A, %d %B %Y %H:%M")
    subject = f"Manifest change - {booking_no}"

    text = (
        f"From:   {name_part} <{sender_email}>\n"
        f"Sent:   {sent}\n"
        f"To:     Manifest Changes\n"
        f"Subject: {subject}\n"
        f"\n"
        f"Hi,\n"
        f"\n"
        f"{payload}\n"
        f"\n"
        f"Thanks,\n"
        f"{name_part}\n"
    )
    return text, sender_email


def main() -> None:
    random.seed(42)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bookings = load_bookings()
    base = datetime(2026, 3, 5, 10, 0)

    rows = []
    for i, pattern in enumerate(ALL_PATTERNS, start=1):
        booking = random.choice(bookings)
        date = base + timedelta(hours=i * 3)
        email_text, sender = build_email(pattern, booking, date)
        out_path = OUT_DIR / f"matched_{i:02d}_{pattern.id}.txt"
        out_path.write_text(email_text, encoding="utf-8")
        rows.append({
            "file": out_path.name,
            "pattern_id": pattern.id,
            "source_dataset": pattern.source,
            "family": pattern.family,
            "technique": pattern.technique,
            "severity": pattern.severity,
            "target_booking": booking["ReleaseNo"],
            "sender": sender,
            "booking_owner_email": sender,
        })

    manifest = ROOT / "red_team" / "manifest_matched.csv"
    with open(manifest, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"Generated {len(rows)} matched-sender poison -> {OUT_DIR}")


if __name__ == "__main__":
    main()
