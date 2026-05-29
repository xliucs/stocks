#!/usr/bin/env python3
"""Pull verified live data for a ticker and compute a normalized score (0-100).

Forward P/E convention (Wall Street standard):
- Uses current fiscal year (FY+0) consensus EPS from yfinance's earnings_estimate
- Falls back to yfinance's info.forwardPE (which is FY+1) when:
  • the ticker reports in a currency different from its quote currency (ADRs), or
  • earnings_estimate is unavailable, or
  • current-FY EPS is non-positive
- This is what Bloomberg / FactSet / most sell-side desks default to.

Score methodology (v3 — adds momentum + policy/regulatory risk):
- Starts at 50
- Analyst upside:     max ±15 pts (dampened — analysts skew bullish)
- Analyst rec:        max ±8  pts
- Forward PE:         max ±12 pts (valuation is key)
- Revenue growth:     max ±8  pts
- Profit margins:     max ±5  pts
- FCF yield:          max ±5  pts
- 52-week position:   max ±7  pts (buying near lows = good, near highs = caution)
- Recent momentum:    max ±8  pts (1-month return; a sharp drop flags a shock that
                                   stale analyst targets haven't repriced yet — so a
                                   crash no longer reads as pure "cheap = buy")
- Policy/regulatory:  0 to -20 (qualitative overlay passed per ticker; captures
                                 active regulatory actions/overhangs that the
                                 quantitative fields are blind to, e.g. the CSRC
                                 mainland-brokerage crackdown that gutted TIGR)

Policy levels (argv[2], default "none"): severe=-20, elevated=-10, moderate=-6, none=0

Rating thresholds: >=68 Bullish, 45-67 Neutral, <45 Bearish
"""
import sys
import json
import yfinance as yf


POLICY_PENALTY = {"severe": -25, "elevated": -12, "moderate": -6, "none": 0}


def compute_forward_pe(t, info):
    """Return Wall Street-standard forward P/E (FY+0) or fall back to yfinance's FY+1.

    See module docstring for convention details.
    """
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if not price or price <= 0:
        return None

    yf_fpe = info.get("forwardPE")  # FY+1 based; in quote currency — always safe fallback
    quote_ccy = info.get("currency", "USD")
    fin_ccy = info.get("financialCurrency", quote_ccy)

    # Only trust earnings_estimate when reporting currency == quote currency
    # (otherwise yfinance returns native-currency estimates against USD ADR price)
    if fin_ccy == quote_ccy:
        try:
            est = t.earnings_estimate
            if est is not None and "0y" in est.index:
                fy0_eps = est.loc["0y", "avg"]
                if fy0_eps and fy0_eps > 0:
                    return price / fy0_eps
        except Exception:
            pass

    return yf_fpe

def compute_momentum(t, info):
    """Return 1-month price return (e.g. -0.25 = down 25%), or None if unavailable.

    A sharp recent drop is a market-priced proxy for a shock (policy, earnings miss,
    fraud flag) that lagging analyst targets haven't caught up to yet — so it should
    temper, not amplify, the "cheap valuation = buy" signal.
    """
    try:
        hist = t.history(period="1mo")
        if hist is None or hist.empty or "Close" not in hist:
            return None
        closes = hist["Close"].dropna()
        if len(closes) < 2:
            return None
        start = float(closes.iloc[0])
        price = info.get("currentPrice") or info.get("regularMarketPrice") or float(closes.iloc[-1])
        if not start or start <= 0:
            return None
        return (price - start) / start
    except Exception:
        return None


def compute_score(info, momentum=None, policy_risk="none"):
    score = 50

    price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
    
    # 1. Analyst upside (max ±15, dampened)
    pt = info.get("targetMeanPrice") or 0
    if price > 0 and pt > 0:
        upside = (pt - price) / price
        # Dampen: 30% upside = +10, 50%+ caps at +15, negative = penalize harder
        if upside >= 0:
            contrib = min(upside * 30, 15)
            # Stale-target guard: after a sharp drop the analyst target predates the
            # shock, so its "upside" is illusory — cap the reward (TIGR failure mode).
            if momentum is not None and momentum <= -0.20:
                contrib = min(contrib, 5)
            score += contrib
        else:
            score += max(upside * 40, -15)
    
    # 2. Analyst recommendation (max ±8)
    rec = info.get("recommendationKey", "").lower()
    rec_map = {"strong_buy": 8, "buy": 5, "outperform": 3, "hold": -2, 
               "underperform": -6, "sell": -8, "strong_sell": -8}
    score += rec_map.get(rec, 0)
    
    # 3. Forward PE attractiveness (max ±12)
    fpe = info.get("forwardPE")
    if fpe and fpe > 0:
        if fpe < 8:    score += 12
        elif fpe < 12: score += 8
        elif fpe < 16: score += 5
        elif fpe < 20: score += 2
        elif fpe < 25: score += 0
        elif fpe < 35: score -= 4
        elif fpe < 50: score -= 8
        else:          score -= 12  # >50x = extremely expensive
    elif fpe and fpe < 0:
        score -= 6  # negative earnings
    
    # 4. Revenue growth (max ±8)
    rev_growth = info.get("revenueGrowth")
    if rev_growth is not None:
        if rev_growth > 0.4:    score += 8
        elif rev_growth > 0.2:  score += 5
        elif rev_growth > 0.1:  score += 3
        elif rev_growth > 0.03: score += 1
        elif rev_growth > -0.05: score -= 1
        elif rev_growth > -0.15: score -= 4
        else:                    score -= 8
    
    # 5. Profitability (max ±5)
    margin = info.get("operatingMargins")
    if margin is not None:
        if margin > 0.3:   score += 5
        elif margin > 0.15: score += 3
        elif margin > 0.05: score += 1
        elif margin > 0:    score += 0
        elif margin > -0.1: score -= 2
        else:               score -= 5
    
    # 6. FCF yield (max ±5)
    fcf = info.get("freeCashflow") or 0
    mcap = info.get("marketCap") or 0
    if mcap > 0 and fcf != 0:
        fcf_yield = fcf / mcap
        if fcf_yield > 0.06:   score += 5
        elif fcf_yield > 0.03: score += 3
        elif fcf_yield > 0.01: score += 1
        elif fcf_yield > 0:    score += 0
        elif fcf_yield < -0.03: score -= 5
        else:                   score -= 2
    
    # 7. 52-week position (max ±7) — buying near lows is better
    hi52 = info.get("fiftyTwoWeekHigh") or 0
    lo52 = info.get("fiftyTwoWeekLow") or 0
    if hi52 > lo52 > 0 and price > 0:
        pos = (price - lo52) / (hi52 - lo52)  # 0 = at 52w low, 1 = at 52w high
        if pos < 0.25:   score += 7   # near lows — contrarian value
        elif pos < 0.4:  score += 4
        elif pos < 0.6:  score += 1
        elif pos < 0.8:  score -= 2
        else:            score -= 5   # near highs — stretched

    # 8. Recent momentum / drawdown (max ±8) — a sharp 1-month drop signals a shock
    # that stale analyst targets haven't repriced; stops a crash from reading as
    # pure "cheap = buy" (this is what made TIGR score 100 after the CSRC crackdown).
    if momentum is not None:
        if momentum <= -0.30:   score -= 8
        elif momentum <= -0.20: score -= 6
        elif momentum <= -0.10: score -= 3
        elif momentum <= 0.10:  score += 0
        elif momentum <= 0.25:  score += 2
        else:                   score += 3   # strong positive momentum

    # 9. Policy / regulatory overlay (0 to -20) — qualitative flag for active
    # regulatory actions or overhangs the quantitative fields can't see.
    score += POLICY_PENALTY.get((policy_risk or "none").lower(), 0)

    return max(0, min(100, round(score)))

def derive_rating(score):
    if score >= 68: return "Bullish"
    if score >= 45: return "Neutral"
    return "Bearish"

def main():
    ticker = sys.argv[1]
    policy_risk = sys.argv[2] if len(sys.argv) > 2 else "none"
    t = yf.Ticker(ticker)
    info = t.info

    price = info.get("currentPrice") or info.get("regularMarketPrice")
    fpe = compute_forward_pe(t, info)
    # Inject the computed fpe back into info so compute_score uses the same convention
    if fpe is not None:
        info["forwardPE"] = fpe
    pt = info.get("targetMeanPrice")
    momentum = compute_momentum(t, info)
    score = compute_score(info, momentum=momentum, policy_risk=policy_risk)
    rating = derive_rating(score)

    result = {
        "price": round(price, 2) if price else None,
        "forwardPE": round(fpe, 1) if fpe and fpe > 0 else None,
        "analystPT": round(pt, 2) if pt else None,
        "score": score,
        "rating": rating,
        "momentum1m": round(momentum, 3) if momentum is not None else None,
        "policyRisk": (policy_risk or "none").lower(),
        "recommendation": info.get("recommendationKey"),
        "revenueGrowth": info.get("revenueGrowth"),
        "operatingMargins": info.get("operatingMargins"),
    }

    print(json.dumps(result))

if __name__ == "__main__":
    main()
