#!/usr/bin/env bash
# setup.sh — drop the compat assets into a Marat-style repo and restart its stack.
#
# Usage from inside compat_pack/:
#     ./setup.sh                       # uses ../  as the target repo
#     TARGET=/path/to/repo ./setup.sh  # explicit target
#
# After this you can:
#     cd $TARGET/src && make restart-app          # if stack already running
#     cd $TARGET/src && make dev                  # if not yet running
#     python compat_pack/tests/run_against_marat.py

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TARGET="${TARGET:-$(cd "$HERE/.." && pwd)}"

echo "Compat pack: $HERE"
echo "Target repo: $TARGET"
echo

# 1. Sanity: target should look like Marat's layout
for d in "$TARGET/data" "$TARGET/emails" "$TARGET/src"; do
    if [ ! -d "$d" ]; then
        echo "❌ $d does not exist. TARGET should point at the Marat-style repo root."
        echo "   Expected: data/, emails/, src/  alongside each other."
        exit 2
    fi
done

# 2. Back up existing CSVs (BookingEmail column is required for entitlement)
echo "→ Backing up your data/*.csv to data/*.csv.bak"
for f in phoenix_bookings_current.csv phoenix_bookings_expected.csv; do
    if [ -f "$TARGET/data/$f" ] && [ ! -f "$TARGET/data/$f.bak" ]; then
        cp "$TARGET/data/$f" "$TARGET/data/$f.bak"
    fi
done

echo "→ Installing updated data/ (adds BookingEmail column needed by entitlement.py)"
cp "$HERE/data/phoenix_bookings_current.csv"  "$TARGET/data/"
cp "$HERE/data/phoenix_bookings_expected.csv" "$TARGET/data/"

# 3. Drop in the new email folders (does NOT touch your existing legit/ or poisonous/)
echo "→ Installing emails/poisonous_extended/ (12 mismatched-sender attacks)"
mkdir -p "$TARGET/emails/poisonous_extended"
cp "$HERE/emails/poisonous_extended/"*.txt "$TARGET/emails/poisonous_extended/"

echo "→ Installing emails/poisonous_extended_matched/ (12 matched-sender stress attacks)"
mkdir -p "$TARGET/emails/poisonous_extended_matched"
cp "$HERE/emails/poisonous_extended_matched/"*.txt "$TARGET/emails/poisonous_extended_matched/"

# 4. Drop in red_team/ for traceability (optional, won't affect runtime)
echo "→ Installing red_team/ (attack pattern library + manifests)"
mkdir -p "$TARGET/red_team"
cp -r "$HERE/red_team/"* "$TARGET/red_team/"

cat <<EOF

✅ Done. Files installed into $TARGET:
   data/phoenix_bookings_current.csv             ← updated (with BookingEmail)
   data/phoenix_bookings_expected.csv            ← updated
   emails/poisonous_extended/        (12 .txt)
   emails/poisonous_extended_matched/(12 .txt)
   red_team/                          (attack patterns + manifests)

Next steps:

   # If your stack is NOT running yet:
   cd $TARGET/src && make dev

   # If your stack IS running, restart it so the new data is picked up:
   cd $TARGET/src && make restart-app

   # Then run the live test:
   python $HERE/tests/run_against_marat.py

If your stack runs on a non-default port:
   BASE_URL=http://localhost:8002 python $HERE/tests/run_against_marat.py

To revert the data overwrite:
   mv $TARGET/data/phoenix_bookings_current.csv.bak $TARGET/data/phoenix_bookings_current.csv
   mv $TARGET/data/phoenix_bookings_expected.csv.bak $TARGET/data/phoenix_bookings_expected.csv

EOF
