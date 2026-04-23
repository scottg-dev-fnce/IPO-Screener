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
| Dimension | Base Weight | Leveraged Issuer Weight |
|---|---|---|
| Business Model Quality | 25% | 25% |
| Market Size & Competitive Position | 20% | 20% |
| Valuation Attractiveness | 20% | **15%** |
| Management & Governance | 20% | 20% |
| Financial Health & Runway | 15% | **20%** |

**Leveraged issuer detection** (auto-computed in Python after Opus returns JSON):
- GAAP-profitable + Debt/Adj.EBITDA >4x → `leveraged_issuer_flag: true`
- GAAP-loss + Debt/Adj.EBITDA >5x → `leveraged_issuer_flag: true`
When triggered: `apply_leverage_adjustments()` recalculates weighted_total with
FHR 20% / VA 15% and appends an adjustment note to scores.adjustments[].
App displays amber banner: "LEVERAGED ISSUER — Financial Health weight increased to 20%."

**Leverage hard floor** (Python-enforced after leverage detection):
- GAAP-profitable + Debt/EBITDA >4x: Financial Health cannot score above 4.0
- GAAP-loss + Debt/AdjEBITDA >6x AND interest expense >20% of revenue: FHR ≤4.0

### Score Thresholds (updated 2026-04-23)
| Score | Band | JSON value | App badge color |
|---|---|---|---|
| ≥75 | UNDERWRITE | `"UNDERWRITE"` | green |
| 65–74 | CONDITIONAL LIGHT | `"CONDITIONAL_LIGHT"` | amber |
| 55–64 | CONDITIONAL HEAVY | `"CONDITIONAL_HEAVY"` | orange |
| <55 | PASS | `"PASS"` | red |

Note: recommendation field uses underscores (`CONDITIONAL_LIGHT`). The app displays
spaces (`CONDITIONAL LIGHT`) via `.replace(/_/g, " ")`.

### Red Flag Deductions
Deduction amounts by severity (applied to the dimension score before weighting):
- CRITICAL → Special treatment (see RF-01A/01B); score_deduction: null
- HIGH     → −2.5 pts from affected dimension (except RF-01A: −4.0)
- MEDIUM   → −1.5 pts from affected dimension
- LOW      → −1.0 pt from affected dimension

**RF-01 split (2026-04-23):**
- **RF-01A GOING CONCERN (CAPITAL-DEFICIENT):** IPO proceeds explicitly resolve the
  going concern. Treatment: CONDITIONAL_HEAVY (not automatic PASS). Deducts 4.0 pts
  from Financial Health. Mandatory disclosure at deal committee.
  Set `going_concern_type: "capital_deficient"`, `going_concern: false`.
- **RF-01B GOING CONCERN (STRUCTURAL):** Fundamental business failure — recurring losses,
  covenant violations, liquidity problems IPO proceeds alone cannot fix.
  Treatment: AUTOMATIC PASS. Set `going_concern: true`, `going_concern_type: "structural"`.
  Python-enforced in `apply_scoring_adjustments()`. Default if ambiguous.

**RF-07 split (2026-04-23):**
- **RF-07 VALUATION DISCONNECT:** Extreme catch-all (>3x sector median). HIGH, −2.5
- **RF-07A EV/REVENUE PREMIUM:** EV/Rev >50% above SIC-matched median. HIGH, −2.5
- **RF-07B EV/EBITDA GROWTH MISMATCH:** EV/EBITDA >25x on GAAP-loss + <30% YoY growth,
  OR EV/EBITDA >35x on any GAAP-loss company. HIGH, −2.5
  **Combined RF-07 cap: max −7.5 pts total from all three.**

**RF-02 customer concentration thresholds (updated 2026-04-23):**
- Top customer >40% revenue: HIGH, −2.5 pts from **Market & Competitive Position**
- Top customer >60% revenue: CRITICAL, −3.0 pts from **Market & Competitive Position**
  (dimension changed from Business Model Quality)

**Management & Governance caps (ISS/Glass Lewis 2025):**
- Dual-class vote ratio >10:1 + no sunset + founder voting >70%: M&G capped at 5.0
  (Python-enforced in `apply_governance_cap()`; set `management_governance_cap_reason`)
- Independent board <50%: deduct 2.5 pts (HIGH)
- No lead independent director: deduct 1.5 pts (MEDIUM)

Automatic PASS override:
- RF-01B structural going concern — Python-enforced in `apply_scoring_adjustments()`
- RF-22 is a strong PASS signal but NOT automatic override

### RF → Dimension Mapping (updated 2026-04-23)
| RF | Name | Dimension | Sev | Deduction |
|---|---|---|---|---|
| RF-01A | Going Concern (Capital-Deficient) | Financial Health | CRITICAL | −4.0, CONDITIONAL |
| RF-01B | Going Concern (Structural) | Financial Health | CRITICAL | AUTO PASS |
| RF-02 | Customer Concentration >40% | **Market Position** | HIGH | −2.5 |
| RF-02 | Customer Concentration >60% | **Market Position** | CRITICAL | −3.0 |
| RF-03 | Revenue Quality | Financial Health | HIGH | −2.5 |
| RF-04 | Insider Liquidity Grab | Mgmt & Governance | HIGH | −2.5 |
| RF-05 | Runway Risk | Financial Health | HIGH | −2.5 |
| RF-06 | Governance Risk | Mgmt & Governance | HIGH | −2.5 |
| RF-07 | Valuation Disconnect (extreme) | Valuation | HIGH | −2.5 |
| RF-07A | EV/Revenue Premium >50% | Valuation | HIGH | −2.5 |
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
| RF-20 | Syndicate Spread Risk | Python post-hoc | HIGH | −1.5/excess, cap −5 |
| RF-21 | PE/Sponsor Overhang | Mgmt & Governance | MEDIUM | −1.5 |
| RF-22 | Small Firm Suitability | (strong PASS) | HIGH | N/A |
| RF-23 | Insider Liquidity Overhang | Mgmt & Governance | MEDIUM | −1.5 |
| RF-24 | Auditor Quality Risk | Financial Health | MEDIUM | −1.5 |
| RF-25 | Accounting Quality Risk | Financial Health + BMQ | HIGH | −2.5 each |

Note: RF-20 is NOT a dimension-level deduction — applied post-hoc by Python to
weighted_total. RF-07 combined cap: max −7.5 from all three RF-07 variants.

### Scoring Floor Rule
If 3+ HIGH or CRITICAL flags trigger, weighted_total must be ≤64 (CONDITIONAL HEAVY
or PASS) unless BMQ and Market Position both ≥8.5.

## MEMO SECTION ORDER (renderMemo + exportPDF)

COVER PAGE — Executive Summary (no section number; part of cover page)
01 Deal Committee Recommendation
02 Business Overview
03 Recommendation Summary — brief statement for UNDERWRITE and PASS only:
     UNDERWRITE: enumerated underwrite_reasons[]
     CONDITIONAL: no Section 03 — the 03C block is self-evident
     PASS: enumerated pass_reasons[]
[03C] Conditions for Underwriting — CONDITIONAL only, no section number badge.
     Full numbered actionable conditions list. Rendered between 03 and 04.
     Styled with amber left border to distinguish from numbered sections.
04 Risk & Red Flags
05 Litigation, Regulatory & Related Party Exposure
06 Financial Snapshot (+ Segment Breakdown if 2+ segments)
07 Use of Proceeds
08 Valuation Analysis (+ SOTP if 2+ segments; Damodaran benchmarks at bottom)
09 Revenue Quality
10 Source Verification
11 Management & Board
12 Macro & Sector Context
13 Underwriting Syndicate
14 Lockup & Insider Selling
15 Syndicate Quality
16 Comparable IPO Performance
17 Auditor Quality
18 Accounting Practices
19 ESG Disclosure Score

## PDF EXPORT RULES

### Part Dividers (inline, not full pages)
- PART I — RECOMMENDATION: before section 01
- PART II — RISK ASSESSMENT: before section 04
- PART III — BUSINESS & FINANCIAL ANALYSIS: before section 06
- PART IV — DEAL STRUCTURE & DILIGENCE: before section 13
- PART V — ESG: before section 19
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

RF-01A: GOING CONCERN (CAPITAL-DEFICIENT) — IPO proceeds explicitly resolve the going concern; solely a pre-IPO capital deficiency. Treatment: CONDITIONAL_HEAVY (not auto-PASS). Deducts 4.0 pts from Financial Health. Set going_concern_type: "capital_deficient".
RF-01B: GOING CONCERN (STRUCTURAL) — Recurring losses, covenant violations, or liquidity problems IPO proceeds alone cannot fix. AUTOMATIC PASS. Set going_concern: true, going_concern_type: "structural". Default if ambiguous.
RF-02: CUSTOMER CONCENTRATION — Top customer >40% = HIGH −2.5 pts from Market Position. Top customer >60% = CRITICAL −3.0 pts from Market Position.
RF-03: REVENUE QUALITY — A/R growing >1.5× faster than revenue; deferred revenue declining despite revenue growth; aggressive non-GAAP adjustments without justification.
RF-04: INSIDER LIQUIDITY GRAB — Secondary shares >30% of offering; founders/sponsors cashing out while company runs losses.
RF-05: RUNWAY RISK — Post-IPO cash runway <18 months at current burn rate.
RF-06: GOVERNANCE RISK — Dual-class with founder voting >70% post-IPO; no independent board majority; classified board.
RF-07: VALUATION DISCONNECT (EXTREME) — Priced >3× sector median EV/Revenue with no justification. Catch-all.
RF-07A: EV/REVENUE PREMIUM — EV/Revenue >50% above SIC-matched sector median. HIGH, −2.5 pts Valuation.
RF-07B: EV/EBITDA GROWTH MISMATCH — EV/EBITDA >25× on GAAP-loss + <30% YoY, OR >35× on any GAAP-loss. HIGH, −2.5 pts. Combined RF-07 cap: max −7.5 pts.
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
RF-22: SMALL FIRM SUITABILITY — Offering size <$50M, or TTM revenue <$10M, or pre-revenue stage. Strong PASS signal (not automatic override).
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

## DEFENSIVE RENDERING LAYER (ipo_screener_app.html)

Three global helpers are defined in the HELPERS section and MUST be used in all section renderers:

### `safeRender(value, opts)`
Converts any value to a display-safe string — never produces `[object Object]`.
- `null/undefined` → opts.fallback (default `"—"`)
- `boolean` → `"Yes"` / `"No"`
- `number` → `String(v)`
- `string` → value or fallback if empty
- `Array` → array items joined with opts.sep (default `", "`); each item recursively safeRender'd
- `Object` → prefers named text fields (`description`, `text`, `name`, `label`, `summary`, `narrative`) else JSON.stringify
- Use for any field that might be a primitive, array, or object depending on schema version.

### `missingDataFlag(sectionLabel)`
Returns an amber warning `<div>` when a section has no data. Use instead of empty string or silent omission.

### `validateMemo(memo)`
Called in `selectCompany()` before `renderMemo()`. Logs `console.warn` for missing or wrong-type critical fields. Do not remove this call.

### Schema Dual-Support Rules
When adding or editing a section renderer:
1. Check both old field name AND new field name with `||` or `??` fallback chains.
2. Use `safeRender()` for any field that is narrative text — never interpolate raw object values.
3. For array-of-objects fields, always `.map()` with field normalization before rendering.
4. Known field aliases (old → new):
   - `m.comparable_ipos` → `m.comparable_ipo_performance.comparable_ipos`
   - `c.offer_price` → `c.ipo_price`
   - `c.first_day_pop_pct` → `c.first_day_return_pct`
   - `c.current_vs_offer_pct` → `c.current_vs_ipo_pct`
   - `fin.revenue_usd_millions.ttm` → `fin.revenue_ttm_usd_millions`
   - `fin.revenue_usd_millions.year_minus_1` → `fin.revenue_prior_year_usd_millions`
   - `fin.revenue_growth_yoy_pct` → `fin.revenue_growth_pct`
   - `fin.cash_on_hand_pre_ipo_usd_millions` → `fin.cash_usd_millions`
   - `uop.growth_capital_pct` (legacy %) → `uop.breakdown[]` (array of objects)
   - `uop.proceeds_flag_rf19` → `uop.rf19_flag`
   - `m.conditions` → `m.conditional_underwrite_conditions`
   - `val.public_comps` (strings) → `val.comparable_companies` (objects)

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

## PDF QUALITY CHECK (MANDATORY)

After every memo generation run, `validate_pdf_output()` runs automatically and prints
a report to stdout. This is non-optional — do not remove or skip this step.

### What it checks
1. **Empty sections** — any of the 13 key memo sections has no renderable content
2. **[object Object] risk** — any field value is a dict/object where a string is expected
3. **Critical fields** — `revenue_ttm_usd_millions`, `gross_margin_pct`, `recommendation`,
   and `deal_committee_recommendation` are null/empty
4. **Part divider targets** — sections 04, 06, 13, and 19 exist and are non-empty
   (these are the sections immediately following Part dividers in the PDF)

### Output format
```
PDF QUALITY CHECK: X issues found [Company Name]
  ⚠ issue description
  ⚠ issue description
  ...
⚠⚠ WARNING: 4+ issues found — memo may render poorly in PDF. Review before distributing.
```

### When issues are found
- Fix the underlying JSON memo fields before distributing the PDF
- If a critical field is missing, re-run analysis or patch the memo manually
- Score ≤5 in `accounting_quality_score` also triggers RF-25 — verify `rf25_triggered` is set

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
