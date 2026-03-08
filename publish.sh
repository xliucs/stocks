#!/bin/bash
# Usage: ./publish.sh <report_html_path> <ticker> <company> <rating> <thesis>
# Example: ./publish.sh /tmp/TSLA_report.html TSLA "Tesla Inc." Bullish "EV leader with AI and energy optionality"

set -e

REPORT_PATH="$1"
TICKER="$2"
COMPANY="$3"
RATING="$4"  # Bullish, Neutral, or Bearish
THESIS="$5"
DATE=$(date +%Y-%m-%d)
DEST_NAME="${TICKER}-${DATE}.html"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ -z "$REPORT_PATH" ] || [ -z "$TICKER" ] || [ -z "$RATING" ]; then
  echo "Usage: ./publish.sh <report_html> <ticker> <company> <rating> <thesis>"
  echo "  rating: Bullish | Neutral | Bearish"
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

# Update reports.json — remove existing entry for same ticker+date, add new one
python3 -c "
import json, sys
ticker, company, date, rating, thesis = sys.argv[1:6]
dest = sys.argv[6]

with open('reports.json', 'r') as f:
    reports = json.load(f)

# Remove existing entry for same ticker+date
reports = [r for r in reports if not (r['ticker'] == ticker and r['date'] == date)]

reports.append({
    'ticker': ticker,
    'company': company,
    'date': date,
    'rating': rating,
    'thesis': thesis,
    'url': f'reports/{dest}'
})

# Sort by date desc, then ticker
reports.sort(key=lambda r: (-int(r['date'].replace('-','')), r['ticker']))

with open('reports.json', 'w') as f:
    json.dump(reports, f, indent=2)

print(f'✅ Updated reports.json ({len(reports)} reports)')
" "$TICKER" "$COMPANY" "$DATE" "$RATING" "$THESIS" "$DEST_NAME"

# Git commit and push
git add -A
git commit -m "Add ${TICKER} valuation report (${DATE})"
git push origin main

echo "🚀 Published ${TICKER} report — live at https://xliucs.github.io/stocks/"
