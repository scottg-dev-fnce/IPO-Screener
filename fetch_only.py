#!/usr/bin/env python3
"""
fetch_only.py
-------------
Fetches the S-1 filing list and raw filing text from EDGAR.
Saves each filing's text to ~/IPO_Screener/raw/{accession_no}.txt
Saves a queue manifest to ~/IPO_Screener/raw/queue.json

Uses Claude Haiku to triage each fetched filing. Non-operating entities
(SPACs, ETFs, trusts, shells) are excluded from queue.json before analysis.

Usage:
  python3 fetch_only.py                            # today only (default)
  python3 fetch_only.py --start 2026-02-20         # Feb 20 through today
  python3 fetch_only.py --start 2026-02-20 --end 2026-02-27  # explicit range
  python3 fetch_only.py --end 2026-02-26           # today through Feb 26

Dedup: filings already present in ~/IPO_Screener/memos/ are always skipped,
regardless of the date range specified.
"""

import re
import json
import time
import logging
import argparse
import requests
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────
# CONFIG (mirrors ipo_screener.py)
# ─────────────────────────────────────────────
LOOKBACK_DAYS       = 7
ALLOWED_FORMS       = {"S-1", "S-1/A"}
MAX_FILINGS         = 10

# Keywords that identify non-operating shell entities — excluded from analysis
EXCLUDE_NAME_KEYWORDS = [
    "acquisition corp", "acquisition corp.", "acquisition co.", "acquisition co ",
    "spac", "blank check", "holding corp",
    " etf", " trust", " fund", " lp", " l.p.",
]
PACIFIC             = ZoneInfo("America/Los_Angeles")
EDGAR_BROWSE        = "https://www.sec.gov/cgi-bin/browse-edgar?company=&CIK=&type=S-1&owner=include&count=100&action=getcurrent"
EDGAR_BASE          = "https://www.sec.gov"
EDGAR_HEADERS       = {"User-Agent": "IPO-Screener research@yourfirm.com"}
RAW_DIR             = Path.home() / "IPO_Screener" / "raw"
DATA_DIR            = Path.home() / "IPO_Screener" / "memos"

RAW_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def _edgar_get(url: str, timeout: int = 60):
    try:
        r = requests.get(url, headers=EDGAR_HEADERS, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        log.warning(f"EDGAR GET failed ({url}): {e}")
        return None


def _strip_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n", strip=True)
    return text[:120000]   # slightly larger cap for Claude Code (no token cost concern)


def _today() -> str:
    return datetime.now(PACIFIC).strftime("%Y-%m-%d")


# ─────────────────────────────────────────────
# CONTENT TRIAGE (keyword matching — no API)
# ─────────────────────────────────────────────

# (keyword, entity_type) — checked in order against the first 15,000 chars of filing text
_TRIAGE_RULES = [
    # Non-operating shells
    ("blank check company",                        "SPAC"),
    ("business combination",                       "SPAC"),
    ("trust account",                              "SPAC"),
    ("exchange-traded fund",                       "ETF"),
    ("exchange traded fund",                       "ETF"),
    # Secondary / follow-on offerings (already-public company selling stockholder shares)
    ("selling stockholders will receive all",      "SECONDARY"),
    ("we will not receive any proceeds",           "SECONDARY"),
    ("all of the shares offered by this prospectus are being sold by the selling", "SECONDARY"),
    ("all proceeds from the sale of shares will be received by the selling",       "SECONDARY"),
    ("our shares of common stock are listed on",   "SECONDARY"),
    ("shares of our common stock are listed on the nasdaq", "SECONDARY"),
    ("shares of our common stock are listed on the new york stock exchange",       "SECONDARY"),
    ("shares of our class a common stock are listed on", "SECONDARY"),
]


def triage_filing_text(text: str, company: str) -> dict:
    """
    Classify a filing as OPERATING_COMPANY or a non-operating entity using keyword
    matching on the first 8,000 characters of the document. No API calls.

    Returns: {"entity_type": str, "skip": bool, "reason": str}
    """
    excerpt = text[:15000].lower()
    for keyword, entity_type in _TRIAGE_RULES:
        if keyword in excerpt:
            reason = f'Filing contains "{keyword}" — classified as {entity_type}'
            log.info(f"  [triage] SKIP {company}: {entity_type} — {reason}")
            return {"entity_type": entity_type, "skip": True, "reason": reason}
    log.info(f"  [triage] PASS {company}: OPERATING_COMPANY")
    return {"entity_type": "OPERATING_COMPANY", "skip": False, "reason": "no non-operating keywords found"}


def _load_saved_accessions() -> set:
    seen = set()
    for json_file in DATA_DIR.rglob("*.json"):
        if json_file.name.startswith("_"):
            continue
        try:
            with open(json_file) as f:
                memo = json.load(f)
            acc = memo.get("accession_no", "")
            if acc:
                seen.add(acc)
        except Exception:
            pass
    return seen


def fetch_filing_list(start_date: str, end_date: str) -> list[dict]:
    log.info(f"Fetching EDGAR browse page — window: {start_date} → {end_date}")

    r = _edgar_get(EDGAR_BROWSE)
    if r is None:
        log.error("Failed to reach EDGAR browse page")
        return []

    soup   = BeautifulSoup(r.text, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        log.error("No tables found on page")
        return []

    filing_table = max(tables, key=lambda t: len(t.find_all("tr")))
    rows         = filing_table.find_all("tr")
    saved        = _load_saved_accessions()

    filings      = []
    company_name = ""
    company_cik  = ""

    for row in rows:
        links = row.find_all("a", href=True)

        cik_link = next((a for a in links if "action=getcompany&CIK=" in a["href"]), None)
        if cik_link:
            raw          = cik_link.get_text(strip=True)
            company_name = re.sub(r"\s*\(\d+\)\s*\(Filer\)", "", raw).strip()
            m            = re.search(r"CIK=(\d+)", cik_link["href"])
            company_cik  = m.group(1).lstrip("0") if m else ""
            continue

        idx_link = next((a for a in links if "-index.htm" in a["href"]), None)
        if not idx_link:
            continue

        tds       = row.find_all("td")
        form_type = tds[0].get_text(strip=True) if tds else ""

        if form_type not in ALLOWED_FORMS:
            log.info(f"  SKIP (form)  {form_type:<10} {company_name}")
            continue

        # Restriction: real operating companies only — exclude SPACs, ETFs, trusts
        name_lower = company_name.lower()
        if any(kw in name_lower for kw in EXCLUDE_NAME_KEYWORDS):
            log.info(f"  SKIP (shell) {form_type:<10} {company_name}")
            continue

        m_acc = re.search(r"/data/\d+/(\d{18})/", idx_link["href"])
        if not m_acc:
            continue
        raw_acc      = m_acc.group(1)
        accession_no = f"{raw_acc[:10]}-{raw_acc[10:12]}-{raw_acc[12:]}"

        row_text    = row.get_text(separator=" ")
        dates       = re.findall(r"(20\d{2}-\d{2}-\d{2})", row_text)
        # For S-1/A rows, the original S-1 date often appears first; take the
        # most recent date so same-day amendments pass the date filter correctly.
        filing_date = max(dates) if dates else end_date

        if filing_date < start_date or filing_date > end_date:
            log.info(f"  SKIP (date)  {filing_date}  {company_name}")
            continue

        if accession_no in saved:
            log.info(f"  SKIP (dup)   {company_name} ({accession_no}) — already analyzed")
            continue

        log.info(f"  QUEUE        {form_type:<8} {filing_date}  {company_name}")
        filings.append({
            "company":      company_name,
            "cik":          company_cik,
            "filing_date":  filing_date,
            "form_type":    form_type,
            "accession_no": accession_no,
            "index_url":    f"{EDGAR_BASE}{idx_link['href']}",
        })

        if len(filings) >= MAX_FILINGS:
            log.info(f"  [CAP] Reached {MAX_FILINGS} filings — stopping")
            break

    return filings



def _pick_primary_from_index_htm(index_htm_url: str) -> str | None:
    """
    Fetch the filing's index.htm page and extract the URL of the primary S-1 document.

    Preference order:
      1. Link whose visible text (or href basename) looks like the main S-1/prospectus
         (excludes exhibits: ex, exhibit, exh in filename)
      2. Largest .htm file (by href order — EDGAR lists primary doc first in most cases)
    """
    r = _edgar_get(index_htm_url, timeout=30)
    time.sleep(0.5)
    if not r:
        return None

    soup  = BeautifulSoup(r.text, "html.parser")
    links = [
        a["href"] for a in soup.find_all("a", href=True)
        if a["href"].startswith("/Archives/")
        and a["href"].lower().endswith((".htm", ".html"))
    ]

    if not links:
        return None

    # Filter out known exhibit patterns
    def is_exhibit(href: str) -> bool:
        name = href.lower().split("/")[-1]
        return any(kw in name for kw in ["ex", "exhibit", "exh", "index"])

    primaries = [l for l in links if not is_exhibit(l)]
    chosen    = primaries[0] if primaries else links[0]
    return f"{EDGAR_BASE}{chosen}"


def fetch_and_save_text(filing: dict) -> str | None:
    """Fetch the S-1 document text and save to RAW_DIR. Returns saved path or None."""
    company      = filing["company"]
    accession_no = filing["accession_no"]
    index_url    = filing.get("index_url", "")

    out_path = RAW_DIR / f"{accession_no}.txt"
    if out_path.exists() and out_path.stat().st_size > 5000:
        log.info(f"  [cached] {out_path.name}")
        return str(out_path)

    # Step 1: parse index.htm to find primary document URL
    log.info(f"  Parsing index: {index_url}")
    primary_url = _pick_primary_from_index_htm(index_url)

    # Step 2: fetch primary document
    if primary_url:
        log.info(f"  Fetching: {primary_url}")
        doc_r = _edgar_get(primary_url, timeout=120)
        time.sleep(1)
        if doc_r:
            text = _strip_html(doc_r.text)
            if len(text) > 5000:
                out_path.write_text(text, encoding="utf-8")
                log.info(f"  Saved {len(text):,} chars → {out_path.name}")
                filing["doc_url"]    = primary_url
                filing["text_chars"] = len(text)
                return str(out_path)
            else:
                log.warning(f"  Document too short ({len(text)} chars) for {company}")

    log.error(f"  All fetch attempts failed for {company} ({accession_no})")
    return None


def _parse_date(s: str) -> str:
    """Validate and normalise a YYYY-MM-DD date string."""
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return s
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date '{s}' — expected YYYY-MM-DD")


def main():
    parser = argparse.ArgumentParser(
        description="Fetch SEC S-1 filings from EDGAR for a given date range.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 fetch_only.py                              # today only\n"
            "  python3 fetch_only.py --start 2026-02-20          # Feb 20 → today\n"
            "  python3 fetch_only.py --start 2026-02-20 --end 2026-02-27\n"
        ),
    )
    today = _today()
    parser.add_argument("--start", metavar="YYYY-MM-DD", type=_parse_date, default=today,
                        help="First filing date to include (default: today)")
    parser.add_argument("--end",   metavar="YYYY-MM-DD", type=_parse_date, default=today,
                        help="Last filing date to include (default: today)")
    args = parser.parse_args()

    if args.start > args.end:
        parser.error(f"--start ({args.start}) must be on or before --end ({args.end})")

    start_date = args.start
    end_date   = args.end
    run_date   = today

    print(f"\n{'='*60}")
    print(f"  EDGAR FETCH ONLY  |  run: {run_date}")
    print(f"  Window: {start_date} → {end_date}  |  Forms: S-1, S-1/A  |  Cap: {MAX_FILINGS}")
    print(f"{'='*60}\n")

    filings = fetch_filing_list(start_date, end_date)
    if not filings:
        print("  No qualifying filings found.\n")
        return

    print(f"\n  {len(filings)} filing(s) queued. Fetching full text...\n")

    queued   = []   # operating companies — passed triage
    skipped  = []   # non-operating entities — excluded by triage

    for i, filing in enumerate(filings, 1):
        print(f"  [{i}/{len(filings)}] {filing['company']} ({filing['form_type']}, {filing['filing_date']})")
        path = fetch_and_save_text(filing)
        filing["raw_text_path"] = path
        filing["fetch_ok"]      = path is not None
        time.sleep(1.5)  # EDGAR courtesy pause between filings

        if not filing["fetch_ok"]:
            queued.append(filing)   # let downstream handle failed fetches
            continue

        # ── Haiku triage: classify entity before queueing for analysis ──
        text = open(path, encoding="utf-8").read() if path else ""
        triage = triage_filing_text(text, filing["company"])
        filing["triage_entity_type"] = triage.get("entity_type", "UNKNOWN")
        filing["triage_reason"]      = triage.get("reason", "")

        if triage.get("skip"):
            print(f"    ✗ SKIP ({triage['entity_type']}) — {triage['reason']}")
            skipped.append(filing)
        else:
            print(f"    ✓ PASS triage ({triage['entity_type']}) — queued for analysis")
            queued.append(filing)

    # Save queue manifest — only operating companies
    queue_path = RAW_DIR / "queue.json"
    with open(queue_path, "w") as f:
        json.dump({"run_date": run_date, "filings": queued}, f, indent=2)

    ok     = sum(1 for f in queued  if f["fetch_ok"])
    failed = sum(1 for f in queued  if not f["fetch_ok"])

    print(f"\n{'─'*60}")
    print(f"  Fetch complete : {ok} OK, {failed} failed")
    print(f"  Triage skipped : {len(skipped)} non-operating ({', '.join(f['triage_entity_type'] for f in skipped) or 'none'})")
    print(f"  Queued for analysis: {len(queued)}")
    print(f"  Raw files  : {RAW_DIR}")
    print(f"  Queue manifest: {queue_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
