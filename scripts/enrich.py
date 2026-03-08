#!/usr/bin/env python3
"""Pull verified live data for a ticker and compute a normalized score (0-100).

Score methodology (v2 — calibrated for realistic distribution):
- Starts at 50
- Analyst upside:     max ±15 pts (dampened — analysts skew bullish)
- Analyst rec:        max ±8  pts
- Forward PE:         max ±12 pts (valuation is key)
- Revenue growth:     max ±8  pts
- Profit margins:     max ±5  pts
- FCF yield:          max ±5  pts
- 52-week position:   max ±7  pts (buying near lows = good, near highs = caution)

Rating thresholds: >=68 Bullish, 45-67 Neutral, <45 Bearish
"""
import sys
import json
import yfinance as yf

def compute_score(info):
    score = 50
    
    price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
    
    # 1. Analyst upside (max ±15, dampened)
    pt = info.get("targetMeanPrice") or 0
    if price > 0 and pt > 0:
        upside = (pt - price) / price
        # Dampen: 30% upside = +10, 50%+ caps at +15, negative = penalize harder
        if upside >= 0:
            score += min(upside * 30, 15)
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
    
    return max(0, min(100, round(score)))

def derive_rating(score):
    if score >= 68: return "Bullish"
    if score >= 45: return "Neutral"
    return "Bearish"

def main():
    ticker = sys.argv[1]
    info = yf.Ticker(ticker).info
    
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    fpe = info.get("forwardPE")
    pt = info.get("targetMeanPrice")
    score = compute_score(info)
    rating = derive_rating(score)
    
    result = {
        "price": round(price, 2) if price else None,
        "forwardPE": round(fpe, 1) if fpe and fpe > 0 else None,
        "analystPT": round(pt, 2) if pt else None,
        "score": score,
        "rating": rating,
        "recommendation": info.get("recommendationKey"),
        "revenueGrowth": info.get("revenueGrowth"),
        "operatingMargins": info.get("operatingMargins"),
    }
    
    print(json.dumps(result))

if __name__ == "__main__":
    main()
