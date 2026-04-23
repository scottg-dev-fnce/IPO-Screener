# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# IPO Screener — ECM Due Diligence Tool
# Regal Securities | Equity Capital Markets
# Maintained by: Scott Goerner

## PROJECT OVERVIEW
Local IPO S-1 screening tool that fetches filings from EDGAR, runs
AI-assisted ECM due diligence analysis, generates structured JSON memos,
and renders them in a browser-based app with PDF export.

- App: http://localhost:8765/ipo_screener_app.html
- Server: python3 -m http.server 8765 (run from ~/IPO_Screener/)
- Memos: ~/IPO_Screener/memos/{YYYY-MM-DD}/{company_name}.json
- Manifest: ~/IPO_Screener/memos/_manifest.json

## CRITICAL RULES — READ BEFORE ANY TASK

### EDGAR / SEC.GOV FETCHING
- NEVER use the fetch tool for any sec.gov or edgar.sec.gov URL
- ALWAYS use bash tool with curl for all EDGAR requests
- Correct User-Agent format: "IPO-Screener contact@regal.com"
- NEVER include an email address in the User-Agent string
- Standard curl command pattern:
  curl -s -A "IPO-Screener contact@regal.com" "https://www.sec.gov/..."
- Filing index URL format:
  https://www.sec.gov/Archives/edgar/data/{CIK}/{accession-no-dashes}/
- Main document search pattern: look for *s1a.htm or *s1.htm in index

### FILE EDITING
- Always read the exact content of a section before editing it
- Use python3 bash scripts for complex multi-line insertions to avoid
  Unicode/encoding issues with str_replace
- After any edit, verify with grep or python3 syntax check
- For ipo_screener.py: python3 -c "import ast; ast.parse(open('file').read())"
- For ipo_screener_app.html: grep for key function names to confirm presence

### JSON MEMO FILES
- Always validate JSON after writing: python3 -m json.tool filename.json
- Update _manifest.json and the date-level _index.json after saving any memo
- Memo filenames: lowercase, spaces replaced with underscores, e.g.
  novacyte_therapeutics.json

## PROJECT STRUCTURE
```
~/IPO_Screener/
├── ipo_screener.py          # Main analysis engine + Claude API calls
├── ipo_screener_app.html    # Browser UI + PDF export
├── memos/
│   ├── _manifest.json       # Master index of all memos
│   └── {YYYY-MM-DD}/
│       ├── _index.json      # Date-level index
│       └── {company}.json   # Individual memo files
└── CLAUDE.md                # This file
```

## SCORING FRAMEWORK

### 5 Dimension Weights
| Dimension | Weight |
|---|---|
| Business Model Quality | 25% |
| Market Size & Competitive Position | 20% |
| Valuation Attractiveness | 20% |
| Management & Governance | 20% |
| Financial Health & Runway | 15% |

### Score Thresholds
- 80-100: UNDERWRITE — present to deal committee
- 60-79: CONDITIONAL — present with conditions noted
- 0-59: PASS — do not present

### Red Flag Deductions
- Each triggered red flag deducts 1.5–3 pts from relevant dimension scores
- RF-25 (accounting quality ≤5) deducts from Financial Health and
  Business Model Quality
- Automatic PASS triggers (regardless of score):
  - RF-01: Going concern audit opinion
  - RF-22: Sub-$50M offering with sub-$10M revenue

## MEMO SECTION ORDER (renderMemo + exportPDF)

01 Executive Summary
02 Deal Committee Recommendation
03 Recommendation Summary — brief one-line statement for all three rec types:
     UNDERWRITE: enumerated underwrite_reasons[]
     CONDITIONAL: "X conditions must be satisfied before this deal can proceed" (no list)
     PASS: enumerated pass_reasons[]
[03C] Conditions for Underwriting — CONDITIONAL only, no section number badge.
     Full numbered actionable conditions list. Rendered between 03 and 04.
     Styled with amber left border to distinguish from numbered sections.
04 Risk & Red Flags
05 Litigation, Regulatory & Related Party Exposure
06 Business Overview
07 Financial Snapshot (+ Segment Breakdown if 2+ segments)
08 Use of Proceeds
09 Valuation Analysis (+ SOTP if 2+ segments; Damodaran benchmarks at bottom)
10 Revenue Quality
11 Source Verification
12 Management & Board
13 Macro & Sector Context
14 Underwriting Syndicate
15 Lockup & Insider Selling
16 Syndicate Quality
17 Comparable IPO Performance
18 Auditor Quality
19 Accounting Practices
20 ESG Disclosure Score

## PDF EXPORT RULES

### Part Dividers (inline, not full pages)
- PART I — RECOMMENDATION: before section 01
- PART II — RISK ASSESSMENT: before section 04
- PART III — BUSINESS & FINANCIAL ANALYSIS: before section 06
- PART IV — DEAL STRUCTURE & DILIGENCE: before section 14
- PART V — ESG: before section 20
- Format: thick 3px gold rule + part title in small caps, single line,
  no page break

### Section 04 Risk & Red Flags (PDF only)
- Render as 3-column table: Flag Name | Severity | Description
- NO RF codes in the Flag column — use plain English name only
  (e.g. "GOING CONCERN" not "RF-01")
- Sort by severity: CRITICAL → HIGH → MEDIUM → LOW
- Remove trailing rubric language from descriptions
  ("AUTOMATIC PASS", "Recommend PASS")
- Suppress narrative paragraph after flag list in PDF
- Keep full display in browser view unchanged

### Section 19 Accounting Practices (PDF only)
- Show ONLY items rated Aggressive or Highly Aggressive
- If all items are Standard/Conservative, show single line:
  "All accounting dimensions rated Standard or Conservative —
  no concerns identified."
- Keep full 8-row table in browser view unchanged

### Cover Page
- REGAL SECURITIES in small caps top left
- "Equity Capital Markets — IPO Due Diligence" subtitle
- Thin rule separating header from company name block
- Company name, ticker, exchange, recommendation badge
- Sector / Offering / Price Range / Auditor / Filed header row
- Score gauge + dimension breakdown
- Amendment banner if applicable

## ESG DISCLOSURE SCORE (Section 20)
- Modeled on Bloomberg ESG Disclosure Score methodology
- Score: 0-100 composite
- Pillars: Environmental (30%), Social (35%), Governance (35%)
- Scores disclosure quality from S-1, not ESG performance
- Schema fields: environmental.score, environmental.highlights[],
  environmental.gaps[], social.score, social.highlights[], social.gaps[],
  governance.score, governance.highlights[], governance.gaps[],
  composite_score, disclosure_narrative

## RED FLAG CODES REFERENCE
These definitions MUST match the system prompt Red Flag Inference Engine exactly.

RF-01: GOING CONCERN — Auditor doubt re: ability to continue as going concern. AUTOMATIC PASS.
RF-02: CUSTOMER CONCENTRATION — Top 3 customers >40% revenue, or top 1 customer >20% revenue.
RF-03: REVENUE QUALITY — A/R growing >1.5× faster than revenue; deferred revenue declining despite revenue growth; aggressive non-GAAP adjustments without justification.
RF-04: INSIDER LIQUIDITY GRAB — Secondary shares >30% of offering; founders/sponsors cashing out while company runs losses.
RF-05: RUNWAY RISK — Post-IPO cash runway <18 months at current burn rate.
RF-06: GOVERNANCE RISK — Dual-class with founder voting >70% post-IPO; no independent board majority; classified board.
RF-07: VALUATION DISCONNECT — Priced >2× sector median EV/Revenue with no superior growth or margin justification.
RF-08: MANAGEMENT RED FLAGS — CEO or CFO tenure <12 months; prior failures or SEC enforcement; key-man concentration without succession.
RF-09: RELATED PARTY RISK — Material revenue from affiliates, loans to executives, above-market IP licensing from insiders.
RF-10: AUDIT ISSUES — Auditor change <24 months without disclosed reason; material weakness in internal controls; non-Big 4 for >$100M revenue company.
RF-11: MARGIN RISK — Gross margin <0% or <20% with no articulated path to improvement; declining margins with increasing scale (inverted unit economics).
RF-12: REGULATORY OVERHANG — Active SEC investigation; DOJ inquiry; material litigation >$50M exposure; adverse imminent regulation.
RF-13: MARKET TIMING RISK — Filing in sector with recent failed IPOs trading significantly below issue price; late-cycle sector.
RF-14: CAPITAL STRUCTURE RISK — PIK debt, high-yield debt with aggressive covenants, or convertible notes with potential dilution >15% of post-IPO shares; Debt/EBITDA >5×.
RF-15: PRODUCT CONCENTRATION — >60% of revenue from a single product/service with no clear diversification roadmap.
RF-16: GEOGRAPHIC CONCENTRATION — >60% revenue from a single geography with no articulated expansion plan.
RF-17: TECHNOLOGY OBSOLESCENCE — Core technology has known near-term substitutes (AI disruption, open-source, platform consolidation).
RF-18: WORKING CAPITAL STRESS — Negative working capital or current ratio <1.0 suggesting near-term liquidity issues.
RF-19: PROCEEDS QUALITY — >30% of gross IPO proceeds to debt repayment, sponsor distributions, or existing shareholder liquidity rather than company operations.
RF-20: SYNDICATE SPREAD RISK — More than 4 lead/co-manager underwriters on a deal below $500M. Signals difficulty placing the book.
RF-21: PE / SPONSOR OVERHANG — PE/sponsor ownership >40% post-IPO with lockup ≤180 days; predictable secondary selling pressure.
RF-22: SMALL FIRM SUITABILITY — Offering size <$50M, or TTM revenue <$10M, or pre-revenue stage. Recommend PASS.
RF-23: INSIDER LIQUIDITY OVERHANG — Secondary shares exceed 20% of total offering.
RF-24: AUDITOR QUALITY RISK — Auditor is not Big 4 or recognized mid-tier on a deal with offering size >$50M.
RF-25: ACCOUNTING QUALITY RISK — Overall Accounting Quality Score ≤5. Multiple aggressive accounting policy choices.

## DAMODARAN INTEGRATION
- Source: NYU Stern Damodaran January 2026 data
- SIC code fetched from EDGAR Submissions API for each company
- Matched to Damodaran industry via _SIC_DAMODARAN_MAP in ipo_screener.py
- Key URLs:
  EV/EBITDA: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/vebitda.html
  EV/Sales: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/psdata.html

## EXISTING MEMOS
| Company | Date | Rec | Score |
|---|---|---|---|
| Novacyte Therapeutics | 2026-02-26 | UNDERWRITE | — |
| Cybriatech Inc. | 2026-02-27 | PASS | — |
| Encore Medical Inc. | 2026-03-03 | PASS | — |
| Cortigent Inc. | 2026-03-05 | PASS | 46 |
| Lendbuzz Inc. | 2026-03-06 | TBD | TBD |

## COMMON ISSUES & FIXES
- Blank pages in PDF: check for .memo-header-wrap not hidden in @media print
- damBench temporal dead zone: define const damBench BEFORE const valSection
- EDGAR 403 errors: never use fetch tool, always curl via bash
- Safari caching: use Chrome for localhost development, Cmd+Shift+R to refresh
- JSON parse errors: use python3 with utf-8 encoding and errors='ignore'

## ARCHITECTURE REFERENCE

### Python Backend (`ipo_screener.py`)
End-to-end pipeline: EDGAR fetch → triage → Claude Opus analysis → JSON memo storage.

Key functions:
- `fetch_new_s1_filings()` — scrapes EDGAR browse page, deduplicates against saved memos, enforces 10-filing/day cap
- `fetch_filing_text()` — fetches primary S-1 document via index parsing; falls back to EDGAR viewer
- `triage_filing()` — keyword-based classifier that skips SPACs, ETFs, secondary offerings before spending Opus tokens
- `analyze_filing()` — sends filing text to Claude Opus with full SYSTEM_PROMPT; handles S-1/A amendment diffing by injecting prior memo context
- `enrich_valuation_with_live_comps()` — fetches live EV/Revenue for comp tickers via yfinance; graceful fallback if not installed
- `enrich_with_damodaran()` — maps company sector to Damodaran industry via SIC code or keyword match
- `apply_scoring_adjustments()` — post-hoc score penalties; re-derives recommendation
- `save_memo()` — writes to memos/{run_date}/{slug}.json; for S-1/A also overwrites prior date file and backs up original

### Fetch Script (`fetch_only.py`)
Decoupled fetcher — identical EDGAR logic but only saves raw text to `raw/` and writes `raw/queue.json`. Used to batch-fetch filings for manual Claude Code analysis without triggering the Anthropic API.

### Memo Writing Rules
- All narrative fields must reflect only the current analysis — never reference prior memos or corrections
- `amendment_changes_summary` stored in JSON for internal record only — never rendered in app or PDF
- `accounting_practices` block with all 8 items required in every memo; score ≤5 triggers RF-25
- Contradiction rule: if any red flag text uses auto-PASS language, `recommendation` field MUST be PASS

### JSON Schema / App Sync
Schema defined in `SYSTEM_PROMPT` inside `ipo_screener.py`. App reads fields directly — adding or renaming top-level fields requires updating both files. Key app-consumed fields: `recommendation`, `scores.weighted_total`, `red_flags`, `red_flag_count`, `going_concern`, `is_amendment`, `executive_summary`, `accounting_practices`, `esg_disclosure`, `damodaran_comps`, `valuation.live_comps_data`.

### Running the Screener
```bash
python3 ipo_screener.py              # Full pipeline
python3 fetch_only.py                # Fetch only, no analysis
python3 -m http.server 8765          # Serve the app
pip install anthropic requests beautifulsoup4 yfinance  # Dependencies
```

## AUTO-BACKUP RULE

At the end of any session where one or more of these files were modified:
- `ipo_screener.py`
- `ipo_screener_app.html`
- `fetch_only.py`
- `save_memos.py`

You MUST run the following before closing out:
```bash
cd ~/IPO_Screener && git add -A && git commit -m "auto-backup" && git push
```

Do this automatically — do not ask for confirmation. The `memos/` folder is excluded
by `.gitignore` so it will never be committed. Run this even if the session ends
mid-task or after a partial change.
