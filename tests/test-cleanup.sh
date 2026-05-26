#!/bin/zsh
# Automated e2e test for the CSV cleanup pipeline.
# This is the workflow that actually works on macOS 15.4+.
set -eu
cd "$(dirname "$0")/.."

OUT=/tmp/apwx-test-out.csv
REPORT=/tmp/apwx-test-report.md
INPUT=tests/fixture.csv

echo "=== test 1: standard mode ==="
python3 scripts/cleanup-csv.py --in "$INPUT" --out "$OUT" --report "$REPORT" 2>&1
ROWS=$(($(wc -l < "$OUT") - 1))
echo "  output rows: $ROWS"
[[ "$ROWS" -lt 22 ]] || { echo "FAIL: expected fewer than 22 rows in standard mode"; exit 1; }
[[ "$ROWS" -gt 12 ]] || { echo "FAIL: expected more than 12 rows in standard mode (subdomain dupes NOT merged)"; exit 1; }
echo "  PASS"

echo ""
echo "=== test 2: aggressive mode ==="
python3 scripts/cleanup-csv.py --in "$INPUT" --out "$OUT" --report "$REPORT" --aggressive 2>&1
ROWS=$(($(wc -l < "$OUT") - 1))
echo "  output rows: $ROWS"
[[ "$ROWS" -eq 12 ]] || { echo "FAIL: expected exactly 12 rows in aggressive mode, got $ROWS"; exit 1; }
echo "  PASS"

echo ""
echo "=== test 3: typo fix ==="
grep -q "sunsthree@gmail.com" "$OUT" && echo "  PASS: .con typo normalized"
grep -q "sunsthree@gmail.con" "$OUT" && { echo "FAIL: typo not fixed"; exit 1; } || true

echo ""
echo "=== test 4: junk removal ==="
grep -q "JunkEntry\|BadEntry" "$OUT" && { echo "FAIL: junk entries still present"; exit 1; } || echo "  PASS: junk removed"

echo ""
echo "=== test 5: title normalization ==="
grep -q "^Snowflakecomputing," "$OUT" && echo "  PASS: domain-style title rewritten"
grep -q "^www.snowflakecomputing.com" "$OUT" && { echo "FAIL: raw domain title still present"; exit 1; } || true

echo ""
echo "=== test 6: dupe selection ==="
AMAZON=$(grep -c ",https://.*amazon.com" "$OUT")
[[ "$AMAZON" -eq 2 ]] || { echo "FAIL: expected 2 Amazon entries (you + mom), got $AMAZON"; exit 1; }
echo "  PASS: $AMAZON Amazon entries kept (Gabriel + Mom, dupes removed)"

echo ""
echo "=== test 7: report generation ==="
[[ -s "$REPORT" ]] || { echo "FAIL: report empty"; exit 1; }
grep -q "## Summary" "$REPORT" || { echo "FAIL: report missing Summary section"; exit 1; }
echo "  PASS: report generated ($(wc -l < "$REPORT") lines)"

echo ""
echo "=== test 8: CSV format compatibility ==="
HEADER=$(head -1 "$OUT" | tr -d '\r')
[[ "$HEADER" == "Title,URL,Username,Password,Notes,OTPAuth" ]] || { echo "FAIL: header changed: '$HEADER'"; exit 1; }
echo "  PASS: header preserved"

echo ""
echo "=== all 8 tests PASSED ==="
echo "cleaned CSV: $OUT"
echo "report:      $REPORT"
