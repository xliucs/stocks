#!/bin/bash
# Aggregator publish: collects all /tmp/<TICKER>_report.html + /tmp/<TICKER>_publish.json
# files produced by parallel research agents, copies them into reports/, rebuilds
# reports.json with verified yfinance data via scripts/enrich.py, then ONE git commit + push.
#
# Usage: ./aggregate_publish.sh
#
# Skips any ticker whose report HTML or publish manifest is missing.

set -e

DATE=$(date +%Y-%m-%d)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Collect every publish manifest in /tmp
MANIFESTS=$(ls /tmp/*_publish.json 2>/dev/null || true)
if [ -z "$MANIFESTS" ]; then
  echo "❌ No /tmp/*_publish.json found — nothing to publish."
  exit 1
fi

mkdir -p reports

# Move HTMLs into reports/ first (skip any whose HTML is missing)
PUBLISHED=()
for manifest in $MANIFESTS; do
  ticker=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['ticker'])" "$manifest")
  html="/tmp/${ticker}_report.html"
  if [ ! -f "$html" ]; then
    echo "⚠️  Skipping $ticker — $html missing"
    continue
  fi
  cp "$html" "reports/${ticker}-${DATE}.html"
  echo "✅ Copied $ticker → reports/${ticker}-${DATE}.html"
  PUBLISHED+=("$ticker")
done

if [ ${#PUBLISHED[@]} -eq 0 ]; then
  echo "❌ No reports could be copied. Aborting."
  exit 1
fi

# Build new reports.json by running enrich.py per ticker (verified live data)
python3 - <<PYEOF
import json, subprocess, sys, os
from pathlib import Path

DATE = "${DATE}"
PUBLISHED = "${PUBLISHED[@]}".split()

with open("reports.json") as f:
    reports = json.load(f)

for ticker in PUBLISHED:
    manifest_path = f"/tmp/{ticker}_publish.json"
    if not os.path.exists(manifest_path):
        print(f"⚠️  No manifest for {ticker}, skipping JSON entry")
        continue
    with open(manifest_path) as f:
        m = json.load(f)

    # Pull verified live data from yfinance
    try:
        out = subprocess.check_output(
            ["uv", "run", "--with", "yfinance", "python3", "scripts/enrich.py", ticker],
            text=True,
            timeout=60,
        )
        live = json.loads(out.strip())
    except Exception as e:
        print(f"⚠️  enrich.py failed for {ticker}: {e}")
        continue

    # Pull next earnings if data file is around
    next_earnings = None
    data_file = f"/tmp/{ticker}_data.json"
    if os.path.exists(data_file):
        with open(data_file) as df:
            try:
                data = json.load(df)
                ne = data.get("earnings_calendar", {}).get("next_earnings_date")
                if ne:
                    next_earnings = ne
            except Exception:
                pass

    # Drop ALL prior entries for this ticker (any date) so we don't accumulate
    # stale duplicates — every refresh fully replaces the ticker's row.
    reports = [r for r in reports if r["ticker"] != ticker]

    reports.append({
        "ticker": ticker,
        "company": m["company"],
        "date": DATE,
        "rating": live["rating"],
        "score": live["score"],
        "category": m.get("categories", []),
        "nextEarnings": next_earnings,
        "price": live["price"],
        "analystPT": live["analystPT"],
        "forwardPE": live["forwardPE"],
        "thesis": m["thesis"],
        "url": f"reports/{ticker}-{DATE}.html",
    })
    print(f"✅ {ticker}: score={live['score']} rating={live['rating']} price=\${live['price']} fwdPE={live['forwardPE']}x PT=\${live['analystPT']}")

# Sort by score desc, ticker asc
reports.sort(key=lambda r: (-(r.get("score") or 0), r["ticker"]))

with open("reports.json", "w") as f:
    json.dump(reports, f, indent=2)

print(f"📝 reports.json now has {len(reports)} entries")
PYEOF

# Single commit + push
git add -A
COUNT=${#PUBLISHED[@]}
TICKER_LIST=$(IFS=,; echo "${PUBLISHED[*]}")
git commit -m "$(cat <<EOF
Refresh ${COUNT} valuation reports — ${DATE}

Tickers: ${TICKER_LIST}

Bulk regeneration with latest 2026 fundamentals, earnings, analyst PTs,
Seeking Alpha + X sentiment, and refreshed catalysts/risks. Live yfinance
data (price, fwd P/E, analyst PT, score, rating) verified per report via
scripts/enrich.py.
EOF
)"

git push origin main

echo ""
echo "🚀 Published ${COUNT} reports → https://xliucs.github.io/stocks/"
echo "   ${TICKER_LIST}"
