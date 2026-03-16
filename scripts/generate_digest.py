#!/usr/bin/env python3
"""Generate a daily market digest entry and save to digest.json.

Pulls market data via yfinance for major indices, sectors, and watchlist
tickers from reports.json. Designed to be run daily via cron.

Usage:
    python3 scripts/generate_digest.py
"""
import json
import os
from datetime import datetime, date

try:
    import yfinance as yf
except ImportError:
    print("Error: yfinance not installed. Run: pip install yfinance")
    raise SystemExit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
REPORTS_JSON = os.path.join(PROJECT_DIR, "reports.json")
DIGEST_JSON = os.path.join(PROJECT_DIR, "digest.json")

INDEX_TICKERS = {
    "SP500": {"symbol": "^GSPC", "name": "S&P 500"},
    "NASDAQ": {"symbol": "^IXIC", "name": "NASDAQ"},
    "DOW": {"symbol": "^DJI", "name": "Dow Jones"},
    "VIX": {"symbol": "^VIX", "name": "VIX"},
}

SECTOR_ETFS = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financials": "XLF",
    "Consumer Discretionary": "XLY",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Communication Services": "XLC",
    "Consumer Staples": "XLP",
}


def get_price_change(symbol):
    """Get current price and daily % change for a symbol."""
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period="2d")
        if len(hist) < 2:
            hist = t.history(period="5d")
        if len(hist) >= 2:
            prev = hist["Close"].iloc[-2]
            curr = hist["Close"].iloc[-1]
            change = (curr - prev) / prev * 100
            return round(curr, 2), round(change, 2)
        elif len(hist) == 1:
            return round(hist["Close"].iloc[-1], 2), 0.0
    except Exception as e:
        print(f"  Warning: Failed to fetch {symbol}: {e}")
    return None, None


def get_index_data():
    """Fetch major index data."""
    indices = {}
    for key, info in INDEX_TICKERS.items():
        print(f"  Fetching {info['name']}...")
        value, change = get_price_change(info["symbol"])
        if value is not None:
            indices[key] = {"value": value, "change": change, "name": info["name"]}
    return indices


def get_sector_data():
    """Fetch sector ETF performance."""
    sectors = {}
    for name, etf in SECTOR_ETFS.items():
        print(f"  Fetching {name} ({etf})...")
        _, change = get_price_change(etf)
        if change is not None:
            sectors[name] = change
    return sectors


def get_watchlist_movers(reports):
    """Get price changes for all watchlist tickers."""
    movers = []
    for r in reports:
        ticker = r["ticker"]
        company = r.get("company", ticker)
        print(f"  Fetching {ticker}...")
        price, change = get_price_change(ticker)
        if price is not None and change is not None:
            movers.append({
                "ticker": ticker,
                "company": company,
                "change": change,
                "price": price,
                "volume": "",
            })
    return movers


def get_upcoming_earnings(reports, days_ahead=10):
    """Find reports with earnings coming up within days_ahead days."""
    today = date.today()
    upcoming = []
    for r in reports:
        earn_date = r.get("nextEarnings")
        if not earn_date:
            continue
        try:
            ed = datetime.strptime(earn_date, "%Y-%m-%d").date()
            delta = (ed - today).days
            if 0 <= delta <= days_ahead:
                upcoming.append({
                    "ticker": r["ticker"],
                    "company": r.get("company", r["ticker"]),
                    "date": earn_date,
                    "status": "upcoming",
                    "estimate": "",
                })
        except ValueError:
            continue
    upcoming.sort(key=lambda x: x["date"])
    return upcoming


def generate_summary(indices, sectors, gainers, losers):
    """Generate a text summary of the market day."""
    parts = []

    sp = indices.get("SP500", {})
    nq = indices.get("NASDAQ", {})
    dj = indices.get("DOW", {})
    vix = indices.get("VIX", {})

    direction = "advanced" if sp.get("change", 0) >= 0 else "declined"
    parts.append(
        f"Markets {direction} on {datetime.now().strftime('%A')}. "
        f"The S&P 500 {'gained' if sp.get('change',0)>=0 else 'fell'} "
        f"{abs(sp.get('change',0)):.2f}% to {sp.get('value','—')}"
    )

    if nq:
        parts.append(
            f", the NASDAQ {'rose' if nq.get('change',0)>=0 else 'dropped'} "
            f"{abs(nq.get('change',0)):.2f}%"
        )
    if dj:
        parts.append(
            f", and the Dow {'climbed' if dj.get('change',0)>=0 else 'slipped'} "
            f"{abs(dj.get('change',0)):.2f}%"
        )
    parts.append(". ")

    if vix:
        parts.append(f"The VIX {'rose' if vix.get('change',0)>=0 else 'fell'} to {vix.get('value','—')}. ")

    best_sector = max(sectors.items(), key=lambda x: x[1]) if sectors else None
    worst_sector = min(sectors.items(), key=lambda x: x[1]) if sectors else None
    if best_sector and worst_sector:
        parts.append(
            f"{best_sector[0]} led sectors (+{best_sector[1]:.1f}%) while "
            f"{worst_sector[0]} lagged ({worst_sector[1]:.1f}%)."
        )

    return "".join(parts)


def main():
    today_str = date.today().isoformat()
    print(f"Generating digest for {today_str}...")

    # Load watchlist from reports.json
    reports = []
    if os.path.exists(REPORTS_JSON):
        with open(REPORTS_JSON) as f:
            reports = json.load(f)
        print(f"Loaded {len(reports)} tickers from reports.json")
    else:
        print("Warning: reports.json not found, skipping watchlist movers")

    # Fetch data
    print("\nFetching index data...")
    indices = get_index_data()

    print("\nFetching sector data...")
    sectors = get_sector_data()

    print("\nFetching watchlist movers...")
    movers = get_watchlist_movers(reports)

    # Sort movers
    gainers = sorted([m for m in movers if m["change"] > 0], key=lambda x: -x["change"])[:5]
    losers = sorted([m for m in movers if m["change"] < 0], key=lambda x: x["change"])[:5]

    # Upcoming earnings
    earnings = get_upcoming_earnings(reports)

    # Generate summary
    summary = generate_summary(indices, sectors, gainers, losers)

    # Build entry
    entry = {
        "date": today_str,
        "summary": summary,
        "indices": indices,
        "sectors": sectors,
        "topGainers": gainers,
        "topLosers": losers,
        "earnings": earnings,
        "news": [],
    }

    # Load existing digest or start fresh
    digest = []
    if os.path.exists(DIGEST_JSON):
        with open(DIGEST_JSON) as f:
            digest = json.load(f)

    # Replace today's entry if it exists, otherwise prepend
    digest = [d for d in digest if d.get("date") != today_str]
    digest.insert(0, entry)

    # Keep last 30 days
    digest = digest[:30]

    with open(DIGEST_JSON, "w") as f:
        json.dump(digest, f, indent=2)

    print(f"\nDigest saved to {DIGEST_JSON}")
    print(f"  Indices: {len(indices)}")
    print(f"  Sectors: {len(sectors)}")
    print(f"  Gainers: {len(gainers)}")
    print(f"  Losers: {len(losers)}")
    print(f"  Upcoming earnings: {len(earnings)}")


if __name__ == "__main__":
    main()
