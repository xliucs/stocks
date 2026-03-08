#!/bin/bash
# Usage: ./publish.sh <report_html_path> <ticker> <company> <thesis> [categories]
# Example: ./publish.sh /tmp/TSLA_report.html TSLA "Tesla Inc." "EV leader with AI optionality" "Mag7,EV"
#
# Price, forward PE, analyst PT, score, and rating are ALL pulled from yfinance.
# No manual numbers needed — everything is verified.

set -e

REPORT_PATH="$1"
TICKER="$2"
COMPANY="$3"
THESIS="$4"
CATEGORIES="$5"  # comma-separated: Mag7,EV,AI
DATE=$(date +%Y-%m-%d)
DEST_NAME="${TICKER}-${DATE}.html"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ -z "$REPORT_PATH" ] || [ -z "$TICKER" ]; then
  echo "Usage: ./publish.sh <report_html> <ticker> <company> <thesis> [categories]"
  echo "  categories: comma-separated (Mag7,EV,AI,Semis,Emerging,Healthcare,Value,Consumer,Fintech,Autonomous,Speculative)"
  echo ""
  echo "Price, P/E, analyst PT, score, and rating are auto-pulled from yfinance."
  exit 1
fi

if [ ! -f "$REPORT_PATH" ]; then
  echo "Error: Report file not found: $REPORT_PATH"
  exit 1
fi

# Copy report
mkdir -p reports
cp "$REPORT_PATH" "reports/${DEST_NAME}"
echo "✅ Copied report to reports/${DEST_NAME}"

# Pull VERIFIED live data from yfinance
echo "📊 Pulling verified data from yfinance for ${TICKER}..."
LIVE_DATA=$(uv run --with yfinance python3 scripts/enrich.py "$TICKER")
echo "   Live data: $LIVE_DATA"

# Update reports.json
python3 -c "
import json, sys

ticker = sys.argv[1]
company = sys.argv[2]
date = sys.argv[3]
thesis = sys.argv[4]
categories = [c.strip() for c in sys.argv[5].split(',') if c.strip()] if sys.argv[5] else []
dest = sys.argv[6]
live = json.loads(sys.argv[7])

with open('reports.json', 'r') as f:
    reports = json.load(f)

# Remove existing entry for same ticker+date
reports = [r for r in reports if not (r['ticker'] == ticker and r['date'] == date)]

# Determine next earnings (try to get from data.json if available)
next_earnings = None
import os
data_file = f'/tmp/{ticker}_data.json'
if os.path.exists(data_file):
    with open(data_file) as df:
        data = json.load(df)
        ne = data.get('earnings_calendar', {}).get('next_earnings_date')
        if ne: next_earnings = ne

reports.append({
    'ticker': ticker,
    'company': company,
    'date': date,
    'rating': live['rating'],
    'score': live['score'],
    'category': categories,
    'nextEarnings': next_earnings,
    'price': live['price'],
    'analystPT': live['analystPT'],
    'forwardPE': live['forwardPE'],
    'thesis': thesis,
    'url': f'reports/{dest}'
})

reports.sort(key=lambda r: (-(r.get('score') or 0), r['ticker']))

with open('reports.json', 'w') as f:
    json.dump(reports, f, indent=2)

print(f'✅ Updated reports.json ({len(reports)} reports) — {ticker}: score={live[\"score\"]}, rating={live[\"rating\"]}, price=\${live[\"price\"]}, fwdPE={live[\"forwardPE\"]}x, PT=\${live[\"analystPT\"]}')
" "$TICKER" "$COMPANY" "$DATE" "$THESIS" "$CATEGORIES" "$DEST_NAME" "$LIVE_DATA"

# Git commit and push
git add -A
git commit -m "Add ${TICKER} valuation report (${DATE}) — score $(echo $LIVE_DATA | python3 -c 'import sys,json;print(json.load(sys.stdin)["score"])')/100"
git push origin main

echo "🚀 Published ${TICKER} report — live at https://xliucs.github.io/stocks/"
