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

**Leverage threshold detection** (Python-detected, no score cap):
- GAAP-profitable + Debt/EBITDA >4x: flags condition, adds note to adjustments
- GAAP-loss + Debt/AdjEBITDA >6x AND interest expense >20% of revenue: flags condition
- No hard cap on FHR — Opus must populate `leverage_assessment` with strategic evaluation
  ending in a one-sentence verdict. Score/recommendation determined by normal framework.

### Score Thresholds (updated 2026-04-23)
| Score | Band | JSON value | App badge color |
|---|---|---|---|
| ≥75 | UNDERWRITE | `"UNDERWRITE"` | green |
| 65–74 | CONDITIONAL LIGHT | `"CONDITIONAL_LIGHT"` | amber |
| 55–64 | CONDITIONAL HEAVY | `"CONDITIONAL_HEAVY"` | orange |
| <55 | PASS | `"PASS"` | red |

Note: recommendation field uses underscores (`CONDITIONAL_LIGHT`). The app displays
spaces (`CONDITIONAL LIGHT`) via `.replace(/_/g, " ")`.

### Auto-PASS Overrides (only two — all others use the scoring framework)
- **RF-01B Structural Going Concern** — Python-enforced; no override possible
- **Pre-Analysis Eligibility Gate** — SPACs, REITs, ETFs, BDCs, etc.; aborted before S-1 fetch
All other flags, including RF-19 (proceeds quality), EV/EBITDA >20x valuation ceiling, and
leverage threshold, contribute to dimension score deductions and require strategic assessment
fields (`proceeds_quality_assessment`, `valuation_ceiling_assessment`, `leverage_assessment`)
but do **not** force any specific recommendation outcome.

### Red Flag Deductions
Deduction amounts by severity (applied to the dimension score before weighting):
- CRITICAL → RF-01B only: AUTOMATIC PASS. All other CRITICAL flags deduct from dimension score.
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
- **PRICE-PENDING RULE:** If `proposed_price_range` is null/empty/TBD, RF-07/07A/07B
  are automatically suppressed by `apply_valuation_rules()` in Python. VA is set to
  6.0 (neutral) with note "Valuation pending — no offering price disclosed." Cover
  page shows "PRICING TBD — valuation deferred" amber badge. When price is later
  disclosed in an amended S-1, flags re-engage normally on the new analysis.

**RF-02 customer concentration thresholds (updated 2026-04-23):**
- Top customer >40% revenue: HIGH, −2.5 pts from **Market & Competitive Position**
- Top customer >60% revenue: CRITICAL, −3.0 pts from **Market & Competitive Position**
  (dimension changed from Business Model Quality)

**Management & Governance — dual-class founder track record assessment (replaces hard cap):**
- For any dual-class structure, Opus assigns `founder_track_record_assessment` in `management{}`.
  Python (`apply_governance_cap()`) applies a deduction based on the tier:
  - `proven_operator` → −1.0 pt from M&G (e.g. Musk/SpaceX, Zuckerberg, Brin/Page)
  - `emerging_operator` → −2.5 pts (domain expertise, limited public CEO experience)
  - `first_time_public_ceo` → −4.0 pts (no prior public company leadership)
  - `concerning_history` → −5.0 pts (governance failures, SEC actions, conflicts)
  - Additional −1.5 pts if founder voting >80% post-IPO AND tier is `first_time_public_ceo` or `concerning_history`
  - If Opus omits the field on a dual-class deal, Python defaults to `emerging_operator`
  - App renders "Founder Track Record" row in Section 11 Management & Board with color coding
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
| RF-23 | Insider Liquidity Overhang (CRITICAL) | Mgmt & Governance | CRITICAL | −3.0 |
| RF-23 | Insider Liquidity Overhang (HIGH) | Mgmt & Governance | HIGH | −2.5 |
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
RF-19: PROCEEDS QUALITY — >30% of gross IPO proceeds to debt repayment, sponsor distributions, or existing shareholder liquidity rather than company operations. HIGH −2.5 pts from M&G. Requires `proceeds_quality_assessment` field with one-sentence verdict. No auto-PASS.
RF-20: SYNDICATE SPREAD RISK — More than 4 lead/co-manager underwriters on a deal below $500M. Signals difficulty placing the book.
RF-21: PE / SPONSOR OVERHANG — PE/sponsor ownership >40% post-IPO with lockup ≤180 days; predictable secondary selling pressure.
RF-22: SMALL FIRM SUITABILITY — Offering size <$50M, or TTM revenue <$10M, or pre-revenue stage. Strong PASS signal (not automatic override).
RF-23: INSIDER LIQUIDITY OVERHANG — Graduated trigger framework (Python enforces deductions):
CRITICAL (−3.0 M&G): Secondary >20% of offering AND lockup_days <180. Combined exit signal.
CRITICAL (−3.0 M&G): No lockup disclosed for any insider class.
HIGH (−2.5 M&G):     Lockup <90 days — below institutional minimum.
HIGH (−2.5 M&G):     Performance-based early release triggerable within 60 days at 10-15% gain.
HIGH (−2.5 M&G):     Material carveouts allowing founders/executives/>5% holders to sell during lockup.
NO TRIGGER:          Standard 90-day-or-longer cliff/rolling lockups with routine de minimis carveouts
                     are institutional norm. 180-day+ cliff with no material carveouts is Investor-Friendly.
                     Python owns all RF-23 deductions; Opus sets rf23_triggered/rf23_reason only.
RF-24: AUDITOR QUALITY RISK — Auditor is not Big 4 or recognized mid-tier on a deal with offering size >$50M.
RF-25: ACCOUNTING QUALITY RISK — Overall Accounting Quality Score ≤5. Multiple aggressive accounting policy choices.

## SECTOR-SPECIFIC VALUATION METRIC FRAMEWORK

Integrated with existing Section 08 Valuation Analysis. Extends — does not replace — the
6-criterion comp framework, RF-07 logic, Damodaran benchmarks, and live_comps_data enrichment.

### How it works
1. `enrich_valuation_metric_selection()` runs in `analyze_filing()` AFTER Opus returns JSON and
   AFTER `enrich_with_damodaran()`, BEFORE `apply_scoring_adjustments()`
2. It calls `select_valuation_metric(sic_code, gaap_profitable, business_model_description,
   segment_count, lease_intensity_pct, capex_intensity_pct)` with inputs computed from the memo
3. Results are injected into `valuation{}` via `setdefault` — Opus-set values preserved if present
4. The 6-criterion comp framework still governs comp selection; methodology only changes which
   metric is calculated on those comps

### Selection Priority Order
| Priority | Condition | sector_classification | primary_metric | secondary_metric |
|---|---|---|---|---|
| 1 | segment_count ≥ 2 | `multi_segment_sotp` | SOTP | EV/EBITDA |
| 2 | SIC 6020/6021/6022 | `bank` | P/B | P/TBV |
| 2 | SIC 6311/6321/6331 | `insurance` | P/B | P/E |
| 2 | SIC 6411 | `insurance_broker` | EV/EBITDA | P/E |
| 2 | SIC 6282 | `asset_manager` | P/E | EV/AUM |
| 2 | SIC 6199/6141/6029 + loan portfolio language | `fintech_balance_sheet` | P/B | P/TBV |
| 2 | SIC 6199/6141/6029 + fee-based platform | `fintech_services` | EV/Revenue | EV/Gross Profit |
| 3 | SIC 1311/1381 | `oil_gas_e_and_p` | EV/EBITDAX | NAV (PV-10) |
| 3 | lease_intensity_pct ≥ 15% | `lease_heavy` | EV/EBITDAR | EV/EBITDA |
| 3 | capex_intensity_pct ≥ 12% | `capex_intensive` | EV/(EBITDA-Capex) | EV/EBITDA |
| 3 | SIC 2834/2836 + no revenue + pipeline lang | `biotech_pre_revenue` | rNPV of pipeline | EV/Peak Sales of lead asset |
| 4 | GAAP-profitable | `standard_profitable` | EV/EBITDA | EV/EBIT |
| 4 | GAAP-loss | `standard_unprofitable` | EV/Revenue | Forward EV/EBITDA |
| 5 (additive) | SIC 7370-7389 + SaaS language | ← | + EV/Subscribers | |
| 5 (additive) | SIC 7370-7389 + social/MAU language | ← | + EV/MAU | |
| 5 (additive) | SIC 7370-7389 + marketplace/GMV language | ← | + EV/GMV | |

### Fintech Sub-Router (critical)
The `fintech_services` vs `fintech_balance_sheet` routing is business-model-driven, not SIC-driven.
A fintech platform with no material loan book (e.g. Chime, payment processor, BaaS provider) uses
`EV/Revenue` / `EV/Gross Profit` even when SIC is in the financial services range — these platforms
trade on tech multiples. A chartered neobank or digital lender with a material loan portfolio uses
`P/B` / `P/TBV` consistent with bank methodology. The router checks `business_model_description`
for loan portfolio / balance sheet lending language.

### RF-07 Sector-Aware Enforcement
- `apply_valuation_rules()` runs RF-07 metric gating on ALL deals (priced and unpriced)
- **RF-07A** (EV/Revenue >50% above sector median) — only fires if `primary_metric` or
  `secondary_metric` contains "EV/Revenue"
- **RF-07B** (EV/EBITDA >25x on loss / >35x any loss company) — only fires if `primary_metric`
  or `secondary_metric` contains "EV/EBITDA"
- **RF-07** (catch-all extreme valuation disconnect) — fires regardless of metric
- Gating only applies when `primary_metric` is set; old memos without the field are unaffected
- Price-pending suppression rule (suppress all RF-07* for unpriced deals) continues to apply

Note: RF-07 threshold calibrations (50% above sector median, 25x/35x EV/EBITDA) currently assume
EV/Revenue and EV/EBITDA. Future refinement may need sector-specific thresholds for P/B, EV/EBITDAX.

### Damodaran Benchmark Routing
`enrich_with_damodaran()` sets `damodaran_comps.primary_benchmark_metric` and `primary_benchmark_value`
based on `sector_classification`:
- `bank` / `fintech_balance_sheet` / `insurance` → P/B from Damodaran pbvdata.html
- `asset_manager` → P/E from Damodaran pedata.html
- `lease_heavy` → EV/EBITDA shown as proxy (Damodaran has no EV/EBITDAR table)
- `multi_segment_sotp` → No single benchmark; segment-specific
- All others → EV/EBITDA (default; existing behavior unchanged)
EV/EBITDA and EV/Revenue are always fetched as reference rows regardless of sector_classification.

### New JSON Fields (valuation{} block)
| Field | Type | Backward-compat default |
|---|---|---|
| `primary_metric` | string | `"EV/EBITDA"` (schema default) |
| `secondary_metric` | string | `"EV/Revenue"` (schema default) |
| `methodology_rationale` | string | `""` (empty = box hidden in renderer) |
| `sector_classification` | string | `"standard_profitable"` (schema default) |
| `sector_specific_metrics` | object | `{}` |

### Renderer Backward Compatibility
Section 08 renderer reads `val.primary_metric` and `val.secondary_metric` with fallback:
- `val.primary_metric || "EV/Revenue"` — defaults to EV/Revenue for old memos
- `val.secondary_metric || "EV/EBITDA"` — defaults to EV/EBITDA for old memos
- Methodology rationale box is hidden when `methodology_rationale` is empty/absent
- Comp table column headers and cell data adapt to selected metrics; old memos render unchanged
- REITs, BDCs, ETFs, closed-end funds remain blocked by the eligibility gate before any of
  this framework runs

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

## PRE-ANALYSIS ELIGIBILITY GATE

This screener is designed exclusively for operating company IPOs.
Non-operating entities (SPACs, blank check companies, REITs, ETFs, closed-end funds,
BDCs, royalty trusts, investment trusts) are automatically aborted before any S-1
content is fetched or any Opus analysis is run.

### Gate function: `validate_company_type(company_name, sic_code, filing_type)`
Called in `analyze_filing()` in two passes:
1. **Pass 1 (before any network call):** checks filing form type and company name only.
2. **Pass 2 (after `fetch_sic_for_cik()`):** checks SIC code in addition to form/name.
The S-1 is only fetched after both passes return `is_eligible=True`.

### Abort conditions (any one triggers abort — no bypass)
| Condition | Entity type |
|---|---|
| SIC 6770 | Blank Check Company |
| SIC 6726 | Investment Office (SPAC / Closed-End Fund / BDC) |
| SIC 6798 | REIT |
| Filing type S-11 | REIT registration |
| Filing type N-2 | Closed-End Fund / BDC registration |
| Name contains: "acquisition corp", "acquisition corporation", "blank check", "spac", "special purpose acquisition" | Blank Check / SPAC |
| Name contains: "royalty trust", "income trust", "investment trust" | Non-operating trust |
| Cover page contains "blank check company" or "no specific business plan" | SPAC (caught by `triage_filing()` after fetch) |

### Abort message format
```
ANALYSIS ABORTED — [Company Name] is a [entity type] based on SIC code [code]
and filing type [type]. This screener is designed for operating company IPOs only.
Non-operating entities are not eligible for ECM due diligence screening.
```

### Do not modify without review
Do not remove or weaken the gate. Do not add a bypass flag. The gate prevents
wasted Opus tokens on ineligible filings and protects the analyst from inadvertently
receiving scoring output on non-operating entities.

## RENDERING RULES (ipo_screener_app.html)

### RF Banner Rule (ENFORCED)
RF-style alert banners belong EXCLUSIVELY in Section 04 (Risk & Red Flags).
Section renderers buildSection10 through buildSection17 must NOT include rf-banner divs.
The rf25Banner in buildSection16 (Accounting Practices) was removed — RF-25 already
appears in the Section 04 flag list. Do not re-add it.

### Comp Selection Exclusion Rule (ENFORCED in system prompt)
Do NOT use semiconductor, hardware, REIT, or colocation companies as comparables
unless the subject company's SIC code and primary revenue model match that sector.
For AI infrastructure / cloud GPU providers, use cloud services or SaaS comps.
Always populate `comp_selection_rationale` explaining each comp choice.

### Multi-Sentence Financial Fields
`covenant_risk` and `off_balance_sheet_obligations` are rendered via `_sentBullets()`:
splits at period/semicolon boundaries into a `<ul>` list for readability.
Apply `_sentBullets(safeRender(value))` to any new financial narrative table row
that may contain multiple sentences.

### Schema Flexibility Rules (safeRender)
- `esg_disclosure.environmental/social/governance` may be strings (narrative) or objects
  → normalized via `_normPillar()` in buildSection17
- `accounting_practices.*` named keys may be strings or objects → buildSection16 fallback
  handles both; string → description only, no risk_rating badge
- `macro_sector_context` may be object or JSON-string-of-object → try JSON.parse first
- `comparable_ipo_performance.recent_comps` is an alias for `.comparable_ipos`
- `comparable_ipo_performance.ipo_market_assessment` is an alias for `.analysis`

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

### lockup_analysis{} Schema (Section 14)

| Field | Type | Description |
|---|---|---|
| `lockup_days` | int | Standard lockup duration in days |
| `lockup_shares_count` | int | Total shares subject to lockup |
| `lockup_pct_of_outstanding` | float | Locked shares as % of post-IPO shares outstanding |
| `lockup_structure_type` | string | `'cliff'` / `'rolling'` / `'performance_based'` / `'hybrid'` |
| `lockup_release_schedule` | array | `[{release_date_days, pct_released, notes}]` for rolling; empty for cliff |
| `early_release_triggers` | array | Each trigger condition as a separate string |
| `parties_locked_up` | array | Who is subject to lockup (founders, executives, investors, etc.) |
| `lockup_carveouts` | array | Material permitted sale exceptions only (omit routine de minimis) |
| `lockup_investor_assessment` | string | Narrative: Investor-Friendly / Standard / Investor-Unfriendly + reasoning. Always populated. |
| `primary_shares_millions` | float | Primary shares in millions |
| `secondary_shares_millions` | float | Secondary shares in millions |
| `secondary_shares_pct_offering` | float | Secondary as % of total offering |
| `rf23_triggered` | bool | Set by Opus for subjective conditions; set by Python for objective |
| `rf23_reason` | string | Specific condition description |

Backward-compat: older memos using `lockup_insider_selling{}` render via field aliases in `buildSection10`.

### RF-23 Graduated Trigger Framework

| Condition | Severity | Deduction | Trigger |
|---|---|---|---|
| Secondary >20% AND lockup <180d | CRITICAL | −3.0 M&G | Combined exit signal |
| No lockup disclosed | CRITICAL | −3.0 M&G | Complete absence |
| Lockup <90 days | HIGH | −2.5 M&G | Below institutional minimum |
| Perf-based early release <60d at 10-15% gain | HIGH | −2.5 M&G | Underwriter accommodation |
| Material carveouts (founders/executives/>5% holders) | HIGH | −2.5 M&G | Undermines lockup purpose |
| 90-day-or-longer cliff/rolling, no material carveouts | **NO TRIGGER** | 0 | Institutional norm |
| 180-day+ cliff, no early release | **Investor-Friendly** | 0 | Explicitly positive |

Python enforces objective conditions (lockup <90d, combined secondary+lockup, no-lockup).
Opus detects subjective conditions (performance triggers, material carveouts) and sets `rf23_triggered`.
Deductions are not stacked — worst single condition applies.

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

## POST-SAVE INDEX VALIDATION (MANDATORY)

After every memo save, `validate_memo_index(run_date)` runs automatically.
**Do not remove or skip this call** — it is what guarantees memos appear in the dashboard.

### What it checks
1. `_index.json` has required top-level fields: `run_date` (str), `run_timestamp` (str), `companies[]` list
2. Each company entry contains: `company_name`, `proposed_ticker`, `recommendation`, `score`, `file`, `filing_date`
3. `_manifest.json` at the memos root includes the current `run_date`

### Auto-repair
If any field is missing or mis-typed, the function rebuilds every entry by reading the saved memo JSON files
on disk and rewrites `_index.json` in the correct schema. The manifest is updated if the date is absent.

### Confirmation output (always printed)
```
  INDEX VALIDATED — memo will appear in dashboard [YYYY-MM-DD]
  INDEX REBUILT — structural mismatch corrected [YYYY-MM-DD]
```

### When writing memos manually (outside the pipeline)
Run `validate_memo_index("YYYY-MM-DD")` after saving any JSON to `memos/{date}/`.
This is the fix for the "memo not showing in dashboard" class of bugs.

### Call sites in ipo_screener.py
- After `save_daily_index([],...)` + `update_manifest(...)` in the no-filings branch
- After `save_daily_index(memos,...)` + `update_manifest(...)` at end of normal run

---

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

## FORWARD-ONLY IMPLEMENTATION RULE

When implementing schema changes, new fields, new sections, or any other feature additions to the IPO screener:

- **Do NOT re-run, re-analyze, regenerate, or backfill any existing memos.** Existing memo JSON files remain untouched. Re-running analyses depletes API usage rapidly and is almost never necessary.
- **All renderers and downstream code must gracefully handle missing fields on older memos** — display `N/A`, hide the element, or fall back cleanly. Never throw errors or break layouts on memos that predate the new field.
- **Changes are forward-only by default.** The next memo run will populate new fields; prior memos stay as-is. If the user wants a specific memo updated, they will explicitly ask.
- **Do not offer to backfill or update existing memos** as part of an implementation. Do not suggest re-running analyses to populate new fields.

### Self-Audit Requirements

After implementing any change, before committing to GitHub, perform a self-audit that verifies process and correctness, not memo regeneration:

1. Re-read every file modified and confirm the new field/feature is wired end-to-end through schema → extraction prompt → JSON output → renderer.
2. Verify backward compatibility: existing memos must still render correctly without the new field present.
3. Confirm no existing functionality broke — composite score, dimension scores, use-of-proceeds tab, comps, and all other elements still render on prior memos.
4. Verify the change is syntactically valid (no Python errors, no JS console errors, no broken HTML).
5. Report any discrepancies found during the audit and fix them before committing.
6. **Do not run analyses on existing companies as part of the audit.** The audit checks code integrity, not data regeneration.

### GitHub Push Rule

Every implementation ends with `git add -A && git commit -m '<descriptive message>' && git push` after the self-audit passes. No implementation is considered complete until pushed to GitHub.

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
