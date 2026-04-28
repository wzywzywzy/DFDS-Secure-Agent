"""
Adapter: wraps generic injection patterns into DFDS email format.

Reads bookings from data_update/phoenix_bookings_current.csv to ensure
we use REAL booking IDs and REAL sender domains — so the attacks are
plausible enough to actually test the authorization layer.

Usage:
    python red_team/adapter.py
    -> writes emails to emails/poisonous_extended/
"""

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

from attack_patterns import ALL_PATTERNS, AttackPattern

ROOT = Path(__file__).resolve().parent.parent
BOOKINGS_CSV = ROOT / "data_update" / "phoenix_bookings_current.csv"
OUT_DIR = ROOT / "emails" / "poisonous_extended"


# Senders we use to construct each attack's "From:" line.
# Mix of legit-looking (matching a booking) and suspicious (mismatched domain).
SUSPICIOUS_SENDERS = [
    ("Pavel Novak", "pavel.novak@globaltrans.example"),       # mismatched domain
    ("M. Anderson", "m.anderson@yolo.example"),               # freemail-style
    ("ops admin", "ops-admin@dfds-support.example"),          # lookalike DFDS
    ("Maria Rossi", "maria.rossi@balticcold.example"),        # legit-looking but wrong booking
]


def load_bookings() -> list[dict]:
    with open(BOOKINGS_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def pick_target_booking(bookings: list[dict], pattern: AttackPattern) -> dict:
    """Pick a booking to target. For cross-account attacks we want one
    whose BookingEmail does NOT match our chosen sender."""
    candidates = [b for b in bookings if b.get("ReleaseNo") and b.get("BookingEmail")]
    return random.choice(candidates)


def build_email(pattern: AttackPattern, booking: dict, sender: tuple[str, str],
                date: datetime) -> str:
    """Wrap a payload as a plausible DFDS customer-service email."""
    sender_name, sender_email = sender
    booking_no = booking["ReleaseNo"]
    payload = pattern.payload.format(booking=booking_no)

    sent = date.strftime("%A, %d %B %Y %H:%M")
    subject = f"Manifest change - {booking_no}"

    return (
        f"From:   {sender_name} <{sender_email}>\n"
        f"Sent:   {sent}\n"
        f"To:     Manifest Changes\n"
        f"Subject: {subject}\n"
        f"\n"
        f"Hi,\n"
        f"\n"
        f"{payload}\n"
        f"\n"
        f"Thanks,\n"
        f"{sender_name}\n"
    )


def main() -> None:
    random.seed(42)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bookings = load_bookings()
    base_date = datetime(2026, 2, 20, 9, 0)

    manifest_rows = []
    for i, pattern in enumerate(ALL_PATTERNS, start=1):
        sender = random.choice(SUSPICIOUS_SENDERS)
        booking = pick_target_booking(bookings, pattern)
        date = base_date + timedelta(hours=i * 3)

        email_text = build_email(pattern, booking, sender, date)
        out_path = OUT_DIR / f"ext_{i:02d}_{pattern.id}.txt"
        out_path.write_text(email_text, encoding="utf-8")

        manifest_rows.append({
            "file": out_path.name,
            "pattern_id": pattern.id,
            "source_dataset": pattern.source,
            "family": pattern.family,
            "technique": pattern.technique,
            "severity": pattern.severity,
            "target_booking": booking["ReleaseNo"],
            "sender": sender[1],
            "booking_owner_email": booking.get("BookingEmail", "(unknown)"),
        })

    manifest_path = OUT_DIR.parent.parent / "red_team" / "manifest.csv"
    with open(manifest_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(manifest_rows[0].keys()))
        w.writeheader()
        w.writerows(manifest_rows)

    print(f"Generated {len(manifest_rows)} extended poison emails -> {OUT_DIR}")
    print(f"Manifest -> {manifest_path}")


if __name__ == "__main__":
    main()
