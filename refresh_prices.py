#!/usr/bin/env python3
"""
refresh_prices.py — Update live market data in any saved memo using yfinance.

Fetches current prices, EV/Revenue, and EV/EBITDA for:
  - valuation.comparable_companies  (Section 08 comp table)
  - comparable_ipo_performance.comparable_ipos  (Section 16 IPO perf table)

Usage:
  python3 refresh_prices.py                        # refresh today's memos
  python3 refresh_prices.py 2026-06-18             # refresh specific date
  python3 refresh_prices.py 2026-06-18 csquare_inc # refresh specific memo

Requires: pip install yfinance
"""

import json
import sys
import time
import glob
import os
from pathlib import Path

MEMOS_DIR = Path(__file__).parent / "memos"


def fetch_ticker_data(yf, ticker: str) -> dict:
    """Return live market data dict for a ticker. Returns {} on failure."""
    try:
        info = yf.Ticker(ticker).info
        ev      = info.get("enterpriseValue")
        rev     = info.get("totalRevenue")
        ebitda  = info.get("ebitda")
        growth  = info.get("revenueGrowth")
        px      = info.get("currentPrice") or info.get("regularMarketPrice")
        name    = info.get("shortName") or info.get("longName")
        time.sleep(0.35)
        return {
            "current_price":        px,
            "ev_usd_millions":      round(ev / 1_000_000) if ev else None,
            "revenue_ttm_usd_millions": round(rev / 1_000_000) if rev else None,
            "ev_revenue_multiple":  round(ev / rev, 1)    if ev and rev and rev > 0 else None,
            "ev_ebitda_multiple":   round(ev / ebitda, 1) if ev and ebitda and ebitda > 0 else None,
            "revenue_growth_pct":   round(growth * 100, 1) if growth is not None else None,
            "name":                 name,
        }
    except Exception as e:
        print(f"  ⚠  {ticker}: yfinance error — {e}")
        return {}


def refresh_valuation_comps(memo: dict, yf) -> int:
    """Refresh EV/Revenue and EV/EBITDA for Section 08 comparable companies. Returns update count."""
    val = memo.get("valuation") or {}
    comps = val.get("comparable_companies") or val.get("public_comps") or []
    if not comps:
        return 0

    updated = 0
    live_comps_data = []
    ev_rev_multiples = []

    for c in comps:
        ticker = (c.get("ticker") or "").strip().upper()
        if not ticker:
            live_comps_data.append(c)
            continue

        print(f"  fetching {ticker}...", end=" ", flush=True)
        data = fetch_ticker_data(yf, ticker)
        if not data:
            live_comps_data.append(c)
            continue

        merged = {**c}
        if data.get("ev_revenue_multiple") is not None:
            merged["ev_revenue"]          = data["ev_revenue_multiple"]
            merged["ev_revenue_multiple"] = data["ev_revenue_multiple"]
            ev_rev_multiples.append(data["ev_revenue_multiple"])
        if data.get("ev_ebitda_multiple") is not None:
            merged["ev_ebitda"]          = data["ev_ebitda_multiple"]
            merged["ev_ebitda_multiple"] = data["ev_ebitda_multiple"]
        if data.get("revenue_growth_pct") is not None:
            merged["revenue_growth_pct"] = data["revenue_growth_pct"]
        if data.get("name"):
            merged.setdefault("name",    data["name"])
            merged.setdefault("company", data["name"])

        live_comps_data.append(merged)
        parts = []
        if data.get("ev_revenue_multiple"): parts.append(f"EV/Rev {data['ev_revenue_multiple']}x")
        if data.get("ev_ebitda_multiple"):  parts.append(f"EV/EBITDA {data['ev_ebitda_multiple']}x")
        print(", ".join(parts) if parts else "no multiples")
        updated += 1

    # Write back — preserve whichever field name the memo uses
    if val.get("comparable_companies") is not None:
        val["comparable_companies"] = live_comps_data
    else:
        val["public_comps"] = live_comps_data

    val["live_comps_data"] = live_comps_data
    memo["live_comps_enriched"] = True

    if ev_rev_multiples:
        median = sorted(ev_rev_multiples)[len(ev_rev_multiples) // 2]
        val["sector_median_ev_revenue"] = median
        val["sector_median_source"]     = "live_market_data"

    memo["valuation"] = val
    return updated


def refresh_ipo_comps(memo: dict, yf) -> int:
    """Refresh current_vs_ipo_pct for Section 16 comparable IPO entries. Returns update count."""
    cip = memo.get("comparable_ipo_performance") or {}
    comps = cip.get("comparable_ipos") or cip.get("recent_comps") or memo.get("comparable_ipos") or []
    if not comps:
        return 0

    updated = 0
    refreshed = []

    for c in comps:
        ticker = (c.get("ticker") or "").strip().upper()
        if not ticker:
            refreshed.append(c)
            continue

        ipo_px = c.get("ipo_price") or c.get("offer_price")
        print(f"  fetching {ticker}...", end=" ", flush=True)
        data = fetch_ticker_data(yf, ticker)

        if not data or not data.get("current_price"):
            print("no price returned")
            refreshed.append(c)
            continue

        current_px = data["current_price"]
        merged = {**c}

        if ipo_px and ipo_px > 0:
            pct = round((current_px - ipo_px) / ipo_px * 100, 1)
            merged["current_vs_ipo_pct"] = pct
            print(f"${ipo_px} → ${current_px:.2f}  ({pct:+.1f}% vs offer)")
        else:
            print(f"current ${current_px:.2f}  (no IPO price stored — skipping pct calc)")

        refreshed.append(merged)
        updated += 1

    # Write back to whichever path the memo uses
    if cip.get("comparable_ipos") is not None or cip.get("recent_comps") is not None:
        cip["comparable_ipos"] = refreshed
        memo["comparable_ipo_performance"] = cip
    else:
        memo["comparable_ipos"] = refreshed

    return updated


def refresh_memo(memo_path: Path, yf) -> None:
    print(f"\n{'─'*60}")
    print(f"  {memo_path.name}")
    print(f"{'─'*60}")

    with open(memo_path, encoding="utf-8") as f:
        memo = json.load(f)

    company = memo.get("company_name", memo_path.stem)
    print(f"  Company : {company}")

    print("  [Section 08] Valuation comps")
    n1 = refresh_valuation_comps(memo, yf)
    print(f"             → {n1} ticker(s) updated")

    print("  [Section 16] IPO performance comps")
    n2 = refresh_ipo_comps(memo, yf)
    print(f"             → {n2} ticker(s) updated")

    if n1 + n2 > 0:
        with open(memo_path, "w", encoding="utf-8") as f:
            json.dump(memo, f, indent=2, ensure_ascii=False)
        print(f"  ✓ Saved — {n1 + n2} total update(s)")
    else:
        print("  — No updates (no tickers found or all fetches failed)")


def main():
    try:
        import yfinance as yf
    except ImportError:
        print("ERROR: yfinance not installed. Run:  pip install yfinance")
        sys.exit(1)

    args = sys.argv[1:]

    if len(args) == 0:
        # Default: refresh today's date folder
        from datetime import date
        target_date = date.today().isoformat()
        date_dirs = [MEMOS_DIR / target_date]
    elif len(args) == 1:
        # Specific date
        target_date = args[0]
        date_dirs = [MEMOS_DIR / target_date]
    else:
        # Specific date + memo slug
        target_date, slug = args[0], args[1]
        memo_file = MEMOS_DIR / target_date / f"{slug}.json"
        if not memo_file.exists():
            print(f"ERROR: memo not found — {memo_file}")
            sys.exit(1)
        refresh_memo(memo_file, yf)
        print("\nDone.")
        return

    for date_dir in date_dirs:
        if not date_dir.exists():
            print(f"No memos found for {date_dir.name}")
            continue
        memo_files = sorted(date_dir.glob("*.json"))
        memo_files = [f for f in memo_files if f.name != "_index.json"]
        if not memo_files:
            print(f"No memo files in {date_dir.name}")
            continue
        for memo_path in memo_files:
            refresh_memo(memo_path, yf)

    print("\nDone.")


if __name__ == "__main__":
    main()
