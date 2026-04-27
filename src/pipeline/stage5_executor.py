"""Stage 5 - executor (writes the approved changes to the Phoenix mock DB).

The "DB" is just the CSV at data_update/phoenix_bookings_current.csv.
Only invoked AFTER human approval. Forbidden-field changes are silently
rejected here as a defense-in-depth measure.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from src.schemas import AuthorizedChange


# Same set as Stage 4. Duplicated intentionally - if Stage 4 is ever
# bypassed, the executor still refuses these.
FORBIDDEN_FIELDS = {
    "Master Hold POD",
    "ENS Hold POD",
    "Customs Hold POD",
    "Com. Code",
    "Cust.Shipref.",
    "Connected ReleaseNo",
}


def apply_changes(csv_path: str | Path, changes: Iterable[AuthorizedChange]) -> dict:
    """Apply the given AuthorizedChange list to the CSV.

    Returns a summary dict {applied: int, skipped: int, errors: list[str]}.
    """
    csv_path = Path(csv_path)
    rows: list[dict[str, str]] = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    applied = 0
    skipped = 0
    errors: list[str] = []

    for change in changes:
        if not change.authorized:
            skipped += 1
            continue
        if change.proposed.field in FORBIDDEN_FIELDS:
            errors.append(
                f"executor refused forbidden field {change.proposed.field} "
                f"on booking {change.proposed.booking_id}"
            )
            skipped += 1
            continue

        target_field = change.proposed.field
        if target_field not in fieldnames:
            errors.append(f"unknown field: {target_field}")
            skipped += 1
            continue

        booking = change.proposed.booking_id
        booking_rows = [r for r in rows if (r.get("ReleaseNo") or "").strip() == booking]
        if not booking_rows:
            errors.append(f"booking {booking} not found in DB")
            skipped += 1
            continue

        # When the booking has multiple line items we update them all by
        # default. A real DB integration would ask the human to pick lines.
        for row in booking_rows:
            row[target_field] = str(change.proposed.new_value)
        applied += 1

    # Write back.
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return {"applied": applied, "skipped": skipped, "errors": errors}
