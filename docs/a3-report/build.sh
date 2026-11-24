#!/usr/bin/env bash
# Build the report PDF from docs/a3-report/report.md and check the 8-page limit for the body.
#   docs/a3-report/build.sh            # writes docs/a3-report/report.pdf
# The appendix (screenshots) starts on its own page and does not count toward the 8 pages: the body
# page count is the page on which <div class="appendix"> begins, minus one.
set -euo pipefail
cd "$(dirname "$0")"
pandoc report.md -f markdown+pipe_tables+raw_html -t html5 -s --metadata title="RAHBAR RAGOps report" -c report.css -o report.html --resource-path=../..:. 2>&1 | grep -v "^\[WARNING\] This document format requires a nonempty <title>" || true
weasyprint report.html report.pdf 2>/dev/null
total=$(pdfinfo report.pdf | awk '/^Pages:/{print $2}')
# body pages = pages before the first page whose text begins the appendix heading
body=$total
for p in $(seq 1 "$total"); do
  if pdftotext -f "$p" -l "$p" report.pdf - | grep -q "^Appendix: screenshots"; then body=$((p-1)); break; fi
done
echo "total pages: $total, body pages: $body (limit 8)"
[ "$body" -le 8 ] || { echo "BODY IS OVER 8 PAGES" >&2; exit 1; }
