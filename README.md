# ECM IPO Due Diligence Screener

**AI-assisted S-1 analysis tool for equity capital markets underwriting decisions.**
Built with Claude Opus 4, Python 3.11+, and a browser-based dashboard.

> **Internal use only — not for distribution.**

---

## What It Does

The screener fetches S-1 and S-1/A filings directly from SEC EDGAR and runs a full 20-section due diligence analysis on each filing before any Opus tokens are spent. Pre-fetch enrichment pulls comparable company multiples, unit economics, and a diligence checklist to inject into the analysis prompt.

Each deal is scored across **5 weighted dimensions**:

| Dimension | Weight |
|---|---|
| Business Model Quality | 25% |
| Market & Competitive Position | 20% |
| Management & Governance | 20% |
| Valuation Attractiveness | 20% |
| Financial Health & Runway | 15% |

**25 red flag rules** are applied with automatic hard stops for structural deal-killers (proceeds quality, accounting quality, going concern). The pipeline produces a PDF-exportable memo with one of four recommendations:

| Recommendation | Score |
|---|---|
| UNDERWRITE | ≥ 75 |
| CONDITIONAL LIGHT | 65 – 74 |
| CONDITIONAL HEAVY | 55 – 64 |
| PASS | < 55 |

The screener automatically aborts before fetching any filing for SPACs, blank check companies, REITs, ETFs, BDCs, and closed-end funds (SIC codes 6770, 6726, 6798 and form types S-11, N-2).

---

## Setup on a New Machine

Run these commands in order:

```bash
# 1. Clone the repository
git clone https://github.com/scottg-dev-fnce/IPO-Screener.git

# 2. Navigate into the project
cd IPO_Screener

# 3. Install dependencies
pip install anthropic requests beautifulsoup4 yfinance

# 4. Set your Anthropic API key
export ANTHROPIC_API_KEY=your_key_here

# 5. Create the local memos folder
mkdir -p memos
```

---

## How to Run an Analysis

Open Claude Code in the `~/IPO_Screener/` directory and use this prompt, replacing `[COMPANY NAME]` with the target company:

```
Analyze [COMPANY NAME] S-1 filing. Pull it fresh from EDGAR, run the full analysis
pipeline with all current scoring rules applied, and save the new memo to the memos folder.
```

Claude Code reads the S-1 directly from EDGAR, runs the full pipeline, and saves the memo to `memos/YYYY-MM-DD/company_name.json`. The memo will appear in the dashboard immediately.

---

## How to View Memos

```bash
# Start the local server
cd ~/IPO_Screener && python3 -m http.server 8765
```

Open in browser: **http://localhost:8765/ipo_screener_app.html**

- Browse sessions by date in the left sidebar
- Click any company to load the full memo
- Export to PDF: `Cmd+P` → Save as PDF (sidebar and filing list are hidden automatically)

---

## File Structure

```
IPO_Screener/
├── ipo_screener.py          # Main pipeline: EDGAR fetch, pre-enrichment,
│                            # Opus analysis, scoring, memo save
├── ipo_screener_app.html    # Browser dashboard: memo viewer, PDF export,
│                            # session management, analytics
├── CLAUDE.md                # Claude Code instruction manual: scoring rules,
│                            # red flag definitions, section structure,
│                            # rendering rules, backup rules
├── fetch_only.py            # Standalone S-1 fetcher for batch pre-fetching
│                            # filings without triggering Opus analysis
├── save_memos.py            # Utility for memo management
└── memos/                   # Local memo storage — excluded from GitHub
    ├── _manifest.json       # Master index of all sessions
    └── YYYY-MM-DD/
        ├── _index.json      # Date-level session index
        └── company_name.json
```

---

## Key Rules

- **Memos are stored locally only** — the `memos/` folder is excluded from GitHub via `.gitignore` and is never pushed
- **Pre-analysis eligibility gate** aborts automatically for SPACs, blank check companies, REITs, ETFs, BDCs, and closed-end funds before any S-1 content is fetched
- **All scoring logic, hard stops, and recommendation thresholds** are documented in `CLAUDE.md` — that file is the authoritative reference for every rule the screener enforces
- **Auto-backup** runs at the end of every Claude Code session that modifies `ipo_screener.py`, `ipo_screener_app.html`, `fetch_only.py`, or `save_memos.py`

---

## Disclaimer

This tool produces AI-assisted analysis derived from publicly available SEC filings. All memos must be reviewed and approved by a licensed capital markets professional before any underwriting decision is made. This analysis does not constitute investment advice or a commitment to underwrite.
