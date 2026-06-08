# IPO Screener — ECM Due Diligence Tool

**AI-assisted S-1 analysis for equity capital markets underwriting decisions.**

Built with Python, Claude AI, and a zero-dependency browser dashboard — no frameworks, no build step, no infrastructure.

---

## See It In Action

View a complete sample memo: [Example.md](Example.md)

---

## Overview

The IPO Screener is a full-stack due diligence automation tool that fetches live S-1 filings from SEC EDGAR, runs structured ECM analysis across 20 memo sections, applies 25 red flag rules with severity-weighted scoring, and renders PDF-exportable memos in a browser dashboard.

Each filing is evaluated against a deterministic scoring framework calibrated to institutional underwriting standards. The pipeline produces a one-of-four recommendation — UNDERWRITE, CONDITIONAL LIGHT, CONDITIONAL HEAVY, or PASS — with a full written memo supporting the conclusion.

---

## Features

- **Live EDGAR integration** — fetches S-1 and S-1/A filings directly from SEC with proper User-Agent headers and rate limiting; no third-party data providers required
- **S-1/A amendment diffing** — detects amendment filings, injects prior memo context, and generates a delta summary highlighting what changed
- **Pre-analysis eligibility gate** — automatically aborts for SPACs, blank check companies, REITs, ETFs, BDCs, and closed-end funds before any analysis runs
- **25-rule red flag engine** — severity-weighted (CRITICAL / HIGH / MEDIUM / LOW) with automatic scoring deductions per dimension
- **Leveraged issuer detection** — auto-shifts Financial Health weight from 15% to 20% and Valuation weight from 20% to 15% when Debt/Adj.EBITDA exceeds thresholds
- **Sector-specific valuation framework** — routes to EV/EBITDA, EV/Revenue, P/B, EV/EBITDAX, EV/EBITDAR, or SOTP based on SIC code and business model
- **Damodaran benchmark integration** — pulls January 2026 NYU Stern sector multiples for calibrated valuation analysis
- **Live comps enrichment** — fetches real-time EV/Revenue for comparable public companies via yfinance
- **ESG disclosure scoring** — Bloomberg-methodology composite across Environmental, Social, and Governance pillars
- **PDF-exportable memos** — `@media print` CSS hides navigation; Section 04 renders as a 3-column severity table; Accounting section shows only flagged items
- **Analytics dashboard** — sector volume chart, avg score by sector, underwrite rate trend, daily filing timeline via Chart.js
- **Watchlist + search** — star companies, filter by recommendation tier, sort by score / offering size / flag count, real-time search
- **CSV export** — download current session to spreadsheet

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  SEC EDGAR                                                       │
│  EDGAR full-text search → submissions API → filing index JSON   │
└──────────────────────┬──────────────────────────────────────────┘
                       │ curl (User-Agent required)
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  ipo_screener.py  (Python backend)                              │
│                                                                  │
│  fetch_new_s1_filings()     EDGAR browse + dedup                │
│  validate_company_type()    Pre-analysis eligibility gate       │
│  fetch_filing_text()        Index parsing → primary doc fetch   │
│  triage_filing()            Keyword classifier (SPAC, ETF, etc) │
│  enrich_valuation_*()       Live comps + Damodaran benchmarks   │
│  analyze_filing()           AI analysis → structured JSON memo  │
│  apply_scoring_adjustments()  Post-hoc: leveraged issuer, RF-20 │
│  save_memo()                Write JSON + update index/manifest  │
└──────────────────────┬──────────────────────────────────────────┘
                       │ JSON files in memos/{date}/
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  ipo_screener_app.html  (browser dashboard, single file)        │
│                                                                  │
│  Session sidebar     Date navigation, watchlist, search/filter  │
│  Memo viewer         20-section render with PDF export          │
│  Analytics tab       4 Chart.js charts, 4 stat cards            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Analysis Pipeline

Each filing passes through the following stages in order:

1. **EDGAR discovery** — scrapes EDGAR full-text search for S-1/S-1/A filings filed in the past N days; deduplicates against saved memos; enforces a 10-filing/day cap
2. **Eligibility gate** — checks SIC code and form type against a blocklist; aborts immediately for non-operating entities
3. **Amendment detection** — if `form_type == S-1/A`, locates the prior memo by slug match and injects the prior summary as context
4. **Pre-enrichment** — pulls comparable company multiples, unit economics proxies, and a diligence checklist to inject into the analysis prompt
5. **Filing fetch** — parses the filing index JSON to identify the primary document; falls back to EDGAR viewer URL
6. **AI analysis** — structured prompt returns a fixed JSON schema with all 20 memo sections, dimension scores, red flags, and accounting quality assessment
7. **Post-hoc adjustments** — Python applies leveraged issuer weight shifts, RF-20 syndicate spread penalty, scoring floor enforcement, and going concern override
8. **Damodaran enrichment** — maps SIC code to NYU Stern industry; fetches EV/EBITDA and EV/Sales sector benchmarks
9. **Live comps enrichment** — fetches real-time EV/Revenue for Claude-selected comp tickers via yfinance
10. **Memo save** — writes JSON to `memos/{date}/{slug}.json`; updates date index and master manifest; runs index validation

---

## Scoring Framework

### Dimension Weights

| Dimension | Standard | Leveraged Issuer |
|---|---|---|
| Business Model Quality | 25% | 25% |
| Market & Competitive Position | 20% | 20% |
| Management & Governance | 20% | 20% |
| Valuation Attractiveness | 20% | **15%** |
| Financial Health & Runway | 15% | **20%** |

Leveraged issuer detection triggers when: GAAP-profitable + Debt/Adj.EBITDA >4x, or GAAP-loss + Debt/Adj.EBITDA >5x.

### Recommendation Thresholds

| Score | Recommendation |
|---|---|
| ≥ 75 | UNDERWRITE |
| 65 – 74 | CONDITIONAL LIGHT |
| 55 – 64 | CONDITIONAL HEAVY |
| < 55 | PASS |

### Scoring Floor Rule

If 3 or more HIGH or CRITICAL flags trigger, `weighted_total` is capped at 64 (CONDITIONAL HEAVY or PASS) unless both Business Model Quality and Market Position score ≥ 8.5/10.

### Auto-PASS Overrides

Only two conditions force an automatic PASS regardless of score:
- **RF-01B Structural Going Concern** — recurring losses or covenant violations that IPO proceeds alone cannot fix
- **Pre-Analysis Eligibility Gate** — SPACs, REITs, ETFs, BDCs, closed-end funds, royalty trusts

---

## Red Flag Engine

25 rules across 6 severity levels. Each flag deducts from its mapped dimension score before weighting.

| Code | Name | Dimension | Sev | Deduction |
|---|---|---|---|---|
| RF-01A | Going Concern (Capital-Deficient) | Financial Health | CRITICAL | −4.0, CONDITIONAL |
| RF-01B | Going Concern (Structural) | Financial Health | CRITICAL | AUTO PASS |
| RF-02 | Customer Concentration >40% | Market Position | HIGH | −2.5 |
| RF-03 | Revenue Quality | Financial Health | HIGH | −2.5 |
| RF-04 | Insider Liquidity Grab | Mgmt & Governance | HIGH | −2.5 |
| RF-05 | Runway Risk | Financial Health | HIGH | −2.5 |
| RF-06 | Governance Risk | Mgmt & Governance | HIGH | −2.5 |
| RF-07 | Valuation Disconnect (extreme) | Valuation | HIGH | −2.5 |
| RF-07A | EV/Revenue Premium >50% above median | Valuation | HIGH | −2.5 |
| RF-07B | EV/EBITDA Growth Mismatch | Valuation | HIGH | −2.5 |
| RF-08 | Management Red Flags | Mgmt & Governance | HIGH | −2.5 |
| RF-09 | Related Party Risk | Mgmt & Governance | MEDIUM | −1.5 |
| RF-10 | Audit Issues | Financial Health | HIGH | −2.5 |
| RF-11 | Margin Risk | Financial Health | HIGH | −2.5 |
| RF-12 | Regulatory Overhang | Business Model | HIGH | −2.5 |
| RF-13 | Market Timing Risk | Market Position | MEDIUM | −1.5 |
| RF-14 | Capital Structure Risk | Financial Health | HIGH | −2.5 |
| RF-15 | Product Concentration | Business Model | MEDIUM | −1.5 |
| RF-16 | Geographic Concentration | Market Position | MEDIUM | −1.5 |
| RF-17 | Technology Obsolescence | Business Model | HIGH | −2.5 |
| RF-18 | Working Capital Stress | Financial Health | MEDIUM | −1.5 |
| RF-19 | Proceeds Quality | Mgmt & Governance | HIGH | −2.5 |
| RF-20 | Syndicate Spread Risk | Post-hoc penalty | HIGH | −1.5/excess, cap −5 |
| RF-21 | PE/Sponsor Overhang | Mgmt & Governance | MEDIUM | −1.5 |
| RF-22 | Small Firm Suitability | (strong PASS signal) | HIGH | N/A |
| RF-23 | Insider Liquidity Overhang | Mgmt & Governance | CRITICAL/HIGH | −3.0/−2.5 |
| RF-24 | Auditor Quality Risk | Financial Health | MEDIUM | −1.5 |
| RF-25 | Accounting Quality Risk | Financial Health + BMQ | HIGH | −2.5 each |

RF-20 is applied post-hoc to `weighted_total` (not a dimension deduction). RF-07 variants are suppressed on unpriced deals (Price-Pending Rule).

---

## Memo Structure

Every memo renders 20 sections plus a cover page:

| # | Section |
|---|---|
| — | Cover Page — Executive Summary |
| 01 | Deal Committee Recommendation |
| 02 | Business Overview |
| 03 | Recommendation Summary (UNDERWRITE/PASS) or Conditions (CONDITIONAL) |
| 04 | Risk & Red Flags |
| 05 | Litigation, Regulatory & Related Party Exposure |
| 06 | Financial Snapshot |
| 07 | Use of Proceeds |
| 08 | Valuation Analysis |
| 09 | Revenue Quality |
| 10 | Source Verification |
| 11 | Management & Board |
| 12 | Macro & Sector Context |
| 13 | Underwriting Syndicate |
| 14 | Lockup & Insider Selling |
| 15 | Syndicate Quality |
| 16 | Comparable IPO Performance |
| 17 | Auditor Quality |
| 18 | Accounting Practices |
| 19 | ESG Disclosure Score |

---

## Setup

```bash
# 1. Clone the repository
git clone https://github.com/scottg-dev-fnce/IPO-Screener.git
cd IPO_Screener

# 2. Install dependencies
pip install anthropic requests beautifulsoup4 yfinance

# 3. Set your Anthropic API key
export ANTHROPIC_API_KEY=your_key_here

# 4. Create the local memos folder
mkdir -p memos
```

**Requirements:** Python 3.11+. `yfinance` is optional — the pipeline falls back gracefully if not installed.

---

## Usage

### Run a new analysis

Open Claude Code in the `~/IPO_Screener/` directory and use this prompt:

```
Analyze [COMPANY NAME] S-1 filing. Pull it fresh from EDGAR, run the full
analysis with all current scoring rules applied, and save the memo to the
memos folder.
```

Claude Code reads the S-1 directly from EDGAR, applies all scoring rules, and writes the memo to `memos/YYYY-MM-DD/company_name.json`.

### View memos

```bash
cd ~/IPO_Screener && python3 -m http.server 8765
```

Open **http://localhost:8765/ipo_screener_app.html**

- Browse sessions by date in the left sidebar
- Click any company to load the full memo
- Filter by recommendation tier (UNDERWRITE / CONDITIONAL / PASS)
- Export to PDF: `Cmd+P` → Save as PDF (sidebar hides automatically via `@media print`)
- Export session to CSV via the CSV button in the topbar

### Batch fetch without analysis

```bash
python3 fetch_only.py
```

Saves raw filing text to `raw/` and writes `raw/queue.json` for manual analysis.

---

## File Structure

```
IPO_Screener/
├── ipo_screener.py          # Main pipeline: EDGAR fetch, enrichment, analysis, scoring
├── ipo_screener_app.html    # Single-file browser dashboard with PDF export
├── fetch_only.py            # Decoupled EDGAR fetcher (no analysis)
├── save_memos.py            # Memo management utilities
├── CLAUDE.md                # Authoritative rule reference for Claude Code sessions
├── SESSION_HANDOFF.md       # Session continuity document
├── LICENSE
└── memos/                   # Local memo storage — excluded from GitHub via .gitignore
    ├── _manifest.json       # Master index of all sessions
    └── YYYY-MM-DD/
        ├── _index.json      # Date-level session index
        └── company_name.json
```

---

## Design Decisions

**Single-file frontend** — `ipo_screener_app.html` is intentionally a single file with no build step, no npm, no bundler. It serves from `python3 -m http.server` and works offline. This keeps the tool portable and deployable anywhere.

**Deterministic scoring** — all scoring rules, deductions, and thresholds are encoded in `CLAUDE.md` and enforced programmatically in `apply_scoring_adjustments()`. The AI analysis populates dimension scores; Python applies all post-hoc adjustments. This keeps the scoring auditable and consistent across sessions.

**EDGAR-first** — raw S-1 text is fetched directly from EDGAR rather than sourced from paid data providers. The filing index JSON (`-index.json`) is parsed to identify the primary document, with a fallback to the EDGAR viewer URL.

**Memos excluded from git** — the `memos/` folder contains AI-generated analysis of public filings and is excluded from version control. The tool ships clean; analysts bring their own memo data.

---

## Disclaimer

This tool produces AI-assisted analysis derived from publicly available SEC filings. All output must be reviewed and approved by a licensed capital markets professional before any underwriting decision is made. This analysis does not constitute investment advice or a commitment to underwrite.

---

## License

MIT — see [LICENSE](LICENSE)
