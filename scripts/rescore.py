#!/usr/bin/env python3
"""Re-score every ticker in reports.json with the v3 enrich.py (momentum + policy).

Policy levels are a qualitative overlay for active regulatory actions/overhangs the
quantitative yfinance fields are blind to. Rationale per ticker below. Levels:
  severe (-20), elevated (-10), moderate (-6), none (0).

Run from repo root:  uv run --with yfinance python3 scripts/rescore.py
"""
import json
import subprocess
import sys
from pathlib import Path

# --- Policy/regulatory risk assignments (independent judgment; edit as needed) ---
POLICY = {
    # severe: active regulatory action directly cripples the core business
    "TIGR": "severe",   # CSRC mainland-brokerage crackdown — the actual cause of the crash
    # elevated: active restriction on a meaningful revenue segment, or acute overhang
    "NVDA": "elevated", # China export controls ban a DC-GPU revenue segment outright
    "WRD":  "elevated", # US-listed Chinese AV: data-security/export scrutiny + delisting overhang
    "PONY": "elevated", # same profile as WRD
    # moderate: real but manageable policy exposure / long-standing overhang
    "BABA": "moderate", # China regulation + HFCAA delisting overhang
    "BILI": "moderate", # China content regulation + delisting overhang
    "NIO":  "moderate", # China EV policy + delisting overhang
    "LI":   "moderate", # China EV policy + delisting overhang
    "XPEV": "moderate", # China EV policy + delisting overhang
    "AMD":  "moderate", # China export controls (smaller exposure than NVDA)
    "TSM":  "moderate", # Taiwan geopolitics + US tariff/export policy
    "MU":   "moderate", # China CAC infra ban on Micron + export controls
    "QCOM": "moderate", # China/Huawei export exposure
    "INTC": "moderate", # heavy CHIPS Act / US-gov stake dependence = policy uncertainty
    "GOOG": "moderate", # active DOJ search-antitrust remedies
    "META": "moderate", # FTC antitrust case
    "AAPL": "moderate", # DOJ antitrust + DMA/App Store regulation
    # everything else: none
}

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports.json"


def enrich(ticker, policy):
    out = subprocess.check_output(
        ["python3", str(ROOT / "scripts" / "enrich.py"), ticker, policy],
        text=True, timeout=90,
    )
    return json.loads(out.strip())


def main():
    reports = json.loads(REPORTS.read_text())
    for r in reports:
        ticker = r["ticker"]
        policy = POLICY.get(ticker, "none")
        try:
            live = enrich(ticker, policy)
        except Exception as e:
            print(f"!! {ticker}: enrich failed: {e}", file=sys.stderr)
            continue
        old_score, old_rating = r.get("score"), r.get("rating")
        r["score"] = live["score"]
        r["rating"] = live["rating"]
        r["price"] = live["price"]
        r["analystPT"] = live["analystPT"]
        r["forwardPE"] = live["forwardPE"]
        r["policyRisk"] = live["policyRisk"]
        r["momentum1m"] = live["momentum1m"]
        mom = live["momentum1m"]
        mom_s = f"{mom:+.0%}" if mom is not None else "n/a"
        print(f"{ticker:5s} {old_score:>3}->{live['score']:>3}  {old_rating:8s}->{live['rating']:8s}"
              f"  policy={policy:8s} 1mo={mom_s}")

    reports.sort(key=lambda r: (-(r.get("score") or 0), r["ticker"]))
    REPORTS.write_text(json.dumps(reports, indent=2) + "\n")
    print(f"\nWrote {len(reports)} entries to {REPORTS}")


if __name__ == "__main__":
    main()
