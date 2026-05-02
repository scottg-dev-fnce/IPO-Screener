# IPO Screener — Session Handoff Document
# Regal Securities | Equity Capital Markets
# Auto-generated: 2026-05-01

This document captures the complete state of the IPO Screener project for seamless
handoff to a new Claude Code session. Read this before starting any task.

---

## 1. PROJECT OVERVIEW

The IPO Screener is a local ECM due diligence tool used by Regal Securities to
evaluate S-1 and S-1/A filings from EDGAR. The system fetches raw filing text,
runs structured due diligence analysis, generates JSON memos with a fixed schema,
and renders them in a dark-themed browser app.

**Key locations:**
- App: http://localhost:8765/ipo_screener_app.html
- Server: `python3 -m http.server 8765` (run from ~/IPO_Screener/)
- Screener: `~/IPO_Screener/ipo_screener.py`
- App UI: `~/IPO_Screener/ipo_screener_app.html`
- Memos: `~/IPO_Screener/memos/{YYYY-MM-DD}/{slug}.json`
- Manifest: `~/IPO_Screener/memos/_manifest.json`
- Daily index: `~/IPO_Screener/memos/{YYYY-MM-DD}/_index.json`
- Raw filings: `~/IPO_Screener/raw_filings/`

**CRITICAL: How analysis actually works.**
Claude Code IS the analysis engine. When asked to run a new memo, you read the raw
filing text directly from disk and produce the JSON memo manually — do NOT call any
Anthropic API or look for ANTHROPIC_API_KEY. `ipo_screener.py` is the schema and
prompt reference; it defines the JSON schema and analysis rules in its SYSTEM_PROMPT
constant. The actual analysis is done by you reading the file and writing the memo.

**EDGAR fetch rule (permanent, non-negotiable):**
NEVER use the WebFetch tool for any sec.gov URL. ALWAYS use Bash with curl:
```bash
curl -s -A "IPO-Screener contact@regal.com" "https://www.sec.gov/..."
```

---

## 2. ALL 19 MEMO SECTIONS — NUMBERS AND RENDERER FUNCTIONS

Sections are rendered by `renderMemo(m)` in `ipo_screener_app.html`. Some sections
are rendered inline inside `renderMemo()`; others have dedicated `buildSectionXX()` functions.

| # | Section Title | Renderer | Notes |
|---|---|---|---|
| — | Cover Page + Executive Summary | Inline in `renderMemo()` | No section number badge; includes score gauge + dimension bars |
| 01 | Deal Committee Recommendation | Inline in `renderMemo()` | `deal_committee_recommendation` field |
| 02 | Business Overview | Inline in `renderMemo()` | `business_overview` field |
| 03 | Recommendation Summary | Inline in `renderMemo()` | UNDERWRITE/PASS only: `underwrite_reasons[]` / `pass_reasons[]` |
| [03C] | Conditions for Underwriting | Inline in `renderMemo()` | CONDITIONAL only; no badge; amber left border |
| 04 | Risk & Red Flags | Inline in `renderMemo()` | `red_flags[]`; PDF: 3-col table, no RF codes, severity-sorted |
| 05 | Litigation, Regulatory & Related Party | `buildSection15(m)` | `litigation_regulatory` + `related_party_flags[]` |
| 06 | Financial Snapshot | Inline in `renderMemo()` | `financials` block + segment table if 2+ segments |
| 07 | Use of Proceeds | Inline in `renderMemo()` | `use_of_proceeds` block |
| 08 | Valuation Analysis | Inline in `renderMemo()` | `valuation` + `damodaran_comps`; SOTP if 2+ segments |
| 09 | Revenue Quality | `buildSection14(m)` | `revenue_quality` block |
| 10 | Source Verification | `buildSectionSourceVerification(m)` | `source_verification` block |
| 11 | Management & Board | `buildSectionManagement(m)` | `management` block |
| 12 | Macro & Sector Context | `buildSection10(m)` | `macro_sector_context` block |
| 13 | Underwriting Syndicate | `buildSection11(m)` | `lead_underwriters[]` + `syndicate_assessment` |
| 14 | Lockup & Insider Selling | `buildSection12(m)` | `lockup_analysis` block |
| 15 | Syndicate Quality | `buildSection13(m)` | `syndicate_quality` block |
| 16 | Comparable IPO Performance | `buildSection10(m)` (NOTE: see below) | `comparable_ipos[]` or `comparable_ipo_performance.comparable_ipos[]` |
| 17 | Auditor Quality | `buildSection13(m)` (NOTE: see below) | `auditor_analysis` block |
| 18 | Accounting Practices | `buildSection16(m)` | `accounting_practices` block |
| 19 | ESG Disclosure Score | `buildSection17(m)` | `esg_disclosure` block |

**Verified renderer → section mapping from grep of app HTML (lines 2413–2817):**
- `buildSection10(m)` → §12 Macro & Sector Context (line 2477)
- `buildSection11(m)` → §13 Underwriting Syndicate (line 2503)
- `buildSection12(m)` → §14 Lockup & Insider Selling (line 2525)
- `buildSection13(m)` → §15 Syndicate Quality (line 2596)
- `buildSection14(m)` → §09 Revenue Quality (line 2621)
- `buildSection15(m)` → §05 Litigation, Regulatory & Related Party (line 2647)
- `buildSection16(m)` → §18 Accounting Practices (line 2680)
- `buildSection17(m)` → §19 ESG Disclosure Score (line 2817)
- `buildSectionSourceVerification(m)` → §10 Source Verification (line 2413)
- `buildSectionManagement(m)` → §11 Management & Board (line 2438)

**Part dividers (PDF, inline — not full pages):**
- PART I — RECOMMENDATION: before §01
- PART II — RISK ASSESSMENT: before §04
- PART III — BUSINESS & FINANCIAL ANALYSIS: before §06
- PART IV — DEAL STRUCTURE & DILIGENCE: before §13
- PART V — ESG: before §19

---

## 3. FULL JSON SCHEMA

Every top-level field and nested object required in every memo. Defined in
`SYSTEM_PROMPT` in `ipo_screener.py` (lines ~870–1155).

```json
{
  "company_name": "",
  "proposed_ticker": "",
  "exchange": "",
  "sector": "",
  "subsector": "",
  "sic_code": "",
  "sic_description": "",
  "offering_size_usd_millions": 0,
  "offering_shares_millions": 0,
  "proposed_price_range": "",
  "lead_underwriters": [],
  "underwriter_tier": "",
  "ipo_type": "",
  "underwriting_type": "",
  "underwriting_subtype": null,
  "underwriting_minimum_raise_usd": null,
  "syndicate_assessment": {
    "underwriter_count": null,
    "spread_risk_flag": false,
    "spread_risk_reason": ""
  },
  "filing_date": "",
  "filing_url": "",
  "auditor": "",
  "auditor_flag": false,

  "financials": {
    "revenue_usd_millions": {"year_minus_2": null, "year_minus_1": null, "ttm": null},
    "revenue_growth_yoy_pct": null,
    "gross_margin_pct": null,
    "gross_margin_trend": "",
    "ebitda_usd_millions": null,
    "adjusted_ebitda_usd_millions": null,
    "net_income_usd_millions": null,
    "cash_burn_quarterly_usd_millions": null,
    "cash_on_hand_pre_ipo_usd_millions": null,
    "estimated_runway_months_post_ipo": null,
    "total_debt_usd_millions": null,
    "stock_based_comp_pct_revenue": null,
    "rule_of_40_score": null,
    "nrr_pct": null,
    "cac_ltv_ratio": null,
    "ar_vs_revenue_growth_flag": false,
    "deferred_revenue_trend": "",
    "debt_maturity_schedule": "",
    "covenant_risk": "",
    "off_balance_sheet_obligations": "",
    "segments": [
      {
        "segment_name": "",
        "revenue_usd_millions": null,
        "gross_margin_pct": null,
        "fcf_usd_millions": null
      }
    ]
  },

  "ownership": {
    "secondary_shares_pct_offering": null,
    "founder_post_ipo_voting_control_pct": null,
    "dual_class_structure": false,
    "lock_up_days": null,
    "lock_up_flag": false,
    "insider_selling_flag": false
  },

  "use_of_proceeds": {
    "growth_capital_pct": null,
    "debt_repayment_pct": null,
    "sponsor_distributions_pct": null,
    "insider_liquidity_pct": null,
    "general_corporate_pct": null,
    "total_non_operational_pct": null,
    "proceeds_flag": false,
    "proceeds_flag_rf19": false,
    "rf19_flag": false,
    "proceeds_narrative": ""
  },

  "management": {
    "ceo_name": "",
    "ceo_tenure_months": null,
    "cfo_name": "",
    "cfo_tenure_months": null,
    "board_independent_pct": null,
    "management_flags": []
  },

  "valuation": {
    "implied_ev_usd_millions": null,
    "ev_revenue_multiple": null,
    "ev_ebitda_multiple": null,
    "sector_median_ev_revenue": null,
    "premium_to_sector_median_pct": null,
    "comparable_companies": [
      {
        "name": "",
        "ticker": "",
        "ev_revenue": null,
        "ev_ebitda": null,
        "revenue_growth_pct": null
      }
    ],
    "public_comps": [],
    "valuation_flag": false,
    "live_comps_data": [],
    "sotp_valuation": {
      "segments": [
        {
          "name": "",
          "methodology": "",
          "implied_value_usd_millions": null
        }
      ],
      "sotp_total_usd_millions": null,
      "sotp_vs_offering_price_delta_pct": null
    }
  },

  "damodaran_comps": {
    "matched_industry": "",
    "ev_ebitda_sector_median": null,
    "ev_revenue_sector_median": null,
    "source": "Damodaran NYU Stern (January 2026)",
    "source_urls": [
      "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/vebitda.html",
      "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/psdata.html"
    ]
  },

  "lockup_analysis": {
    "lockup_days": null,
    "primary_shares_millions": null,
    "secondary_shares_millions": null,
    "secondary_shares_pct_offering": null,
    "lockup_carveouts": "",
    "rf23_triggered": false,
    "rf23_reason": ""
  },

  "syndicate_quality": {
    "lead_bookrunner": "",
    "lead_bookrunner_tier": "",
    "tier_assessment": "",
    "rf20_tier3_flag": false,
    "rf20_tier3_reason": ""
  },

  "comparable_ipos": [
    {
      "company": "",
      "ticker": "",
      "ipo_date": "",
      "sector": "",
      "offer_price": null,
      "ipo_price": null,
      "first_day_pop_pct": null,
      "first_day_return_pct": null,
      "current_vs_offer_pct": null,
      "current_vs_ipo_pct": null,
      "comp_type": "",
      "comp_selection_rationale": "",
      "notes": ""
    }
  ],

  "auditor_analysis": {
    "auditor_name": "",
    "auditor_tier": "",
    "material_weaknesses": false,
    "rf24_triggered": false,
    "rf24_reason": ""
  },

  "revenue_quality": {
    "recurring_vs_nonrecurring": "",
    "contracted_vs_transactional": "",
    "organic_vs_acquisition_driven": "",
    "quality_rating": "",
    "quality_narrative": ""
  },

  "litigation_regulatory": {
    "pending_sec_investigations": false,
    "pending_finra_actions": false,
    "class_action_suits": false,
    "material_regulatory_proceedings": false,
    "litigation_summary": "",
    "litigation_risk_level": ""
  },

  "red_flags": [
    {
      "code": "RF-XX",
      "name": "",
      "severity": "HIGH|MEDIUM|LOW|CRITICAL",
      "triggered": true,
      "description": "",
      "affected_dimension": "",
      "score_deduction": 2.5
    }
  ],
  "red_flag_count": 0,
  "going_concern": false,
  "going_concern_type": null,
  "leveraged_issuer_flag": false,
  "management_governance_cap_reason": null,

  "scores": {
    "business_model_quality": null,
    "financial_health_runway": null,
    "market_competitive_position": null,
    "management_governance": null,
    "valuation_attractiveness": null,
    "weighted_total": null,
    "fhr_weight_used": 0.15,
    "va_weight_used": 0.20,
    "adjustments": []
  },

  "recommendation": "",
  "underwrite_reasons": [],
  "conditions": [],
  "conditional_underwrite_conditions": [],
  "pass_reasons": [],

  "executive_summary": "",
  "business_overview": "",
  "key_risk_narrative": "",
  "related_party_flags": [],
  "macro_sector_context": {
    "sector_thesis": "",
    "market_timing": "",
    "bull_case": [],
    "bear_case": []
  },
  "deal_committee_recommendation": "",

  "accounting_practices": {
    "items": [
      {
        "category": "Revenue Recognition",
        "key": "revenue_recognition",
        "description": "",
        "assessment": "",
        "earnings_impact": "",
        "risk_rating": "Conservative|Standard|Aggressive|Highly Aggressive"
      },
      {
        "category": "Cost Capitalization",
        "key": "cost_capitalization",
        "description": "",
        "assessment": "",
        "earnings_impact": "",
        "risk_rating": ""
      },
      {
        "category": "Lease Classification",
        "key": "lease_classification",
        "description": "",
        "assessment": "",
        "earnings_impact": "",
        "risk_rating": ""
      },
      {
        "category": "Goodwill & Intangible Impairment",
        "key": "goodwill_impairment",
        "description": "",
        "assessment": "",
        "earnings_impact": "",
        "risk_rating": ""
      },
      {
        "category": "Depreciation & Amortization",
        "key": "depreciation_amortization",
        "description": "",
        "assessment": "",
        "earnings_impact": "",
        "risk_rating": ""
      },
      {
        "category": "Pension & Benefit Obligations",
        "key": "pension_obligations",
        "description": "",
        "assessment": "",
        "earnings_impact": "",
        "risk_rating": ""
      },
      {
        "category": "Non-GAAP Metrics",
        "key": "non_gaap_metrics",
        "description": "",
        "assessment": "",
        "earnings_impact": "",
        "risk_rating": ""
      },
      {
        "category": "Related Party Disclosures",
        "key": "related_party_disclosures",
        "description": "",
        "assessment": "",
        "earnings_impact": "",
        "risk_rating": ""
      }
    ],
    "accounting_quality_score": null,
    "rf25_triggered": false,
    "rf25_reason": "",
    "accounting_quality_summary": ""
  },

  "esg_disclosure": {
    "environmental": {
      "score": null,
      "highlights": [],
      "gaps": []
    },
    "social": {
      "score": null,
      "highlights": [],
      "gaps": []
    },
    "governance": {
      "score": null,
      "highlights": [],
      "gaps": []
    },
    "composite_score": null,
    "weights": {"e": 0.30, "s": 0.35, "g": 0.35},
    "disclosure_narrative": ""
  },

  "source_verification": {
    "tier_1_sources": [],
    "tier_2_sources": [],
    "tier_3_sources": []
  },

  "is_amendment": false,
  "prior_memo_date": null,
  "amendment_changes_summary": null
}
```

**Key field aliases (old → new) — renderers handle both via fallback chains:**
- `m.comparable_ipos` → `m.comparable_ipo_performance.comparable_ipos`
- `c.offer_price` → `c.ipo_price`
- `c.first_day_pop_pct` → `c.first_day_return_pct`
- `c.current_vs_offer_pct` → `c.current_vs_ipo_pct`
- `fin.revenue_usd_millions.ttm` → `fin.revenue_ttm_usd_millions`
- `fin.revenue_usd_millions.year_minus_1` → `fin.revenue_prior_year_usd_millions`
- `fin.revenue_growth_yoy_pct` → `fin.revenue_growth_pct`
- `fin.cash_on_hand_pre_ipo_usd_millions` → `fin.cash_usd_millions`
- `uop.proceeds_flag_rf19` → `uop.rf19_flag`
- `m.conditions` → `m.conditional_underwrite_conditions`
- `val.public_comps` (strings) → `val.comparable_companies` (objects)

---

## 4. ALL 25 RED FLAG DEFINITIONS

Source: `ipo_screener.py` SYSTEM_PROMPT, lines ~560–700.

| Code | Name | Dimension | Severity | Deduction |
|---|---|---|---|---|
| RF-01A | Going Concern (Capital-Deficient) | Financial Health | CRITICAL | −4.0 pts; CONDITIONAL_HEAVY |
| RF-01B | Going Concern (Structural) | Financial Health | CRITICAL | AUTO PASS; no numeric deduction |
| RF-02 | Customer Concentration >40% | Market Position | HIGH | −2.5 pts |
| RF-02 | Customer Concentration >60% | Market Position | CRITICAL | −3.0 pts |
| RF-03 | Revenue Quality | Financial Health | HIGH | −2.5 pts |
| RF-04 | Insider Liquidity Grab | Mgmt & Governance | HIGH | −2.5 pts |
| RF-05 | Runway Risk | Financial Health | HIGH | −2.5 pts |
| RF-06 | Governance Risk | Mgmt & Governance | HIGH | −2.5 pts |
| RF-07 | Valuation Disconnect (Extreme) | Valuation | HIGH | −2.5 pts (catch-all >3x median) |
| RF-07A | EV/Revenue Premium >50% | Valuation | HIGH | −2.5 pts |
| RF-07B | EV/EBITDA Growth Mismatch | Valuation | HIGH | −2.5 pts; combined RF-07 cap −7.5 total |
| RF-08 | Management Red Flags | Mgmt & Governance | HIGH | −2.5 pts |
| RF-09 | Related Party Risk | Mgmt & Governance | MEDIUM | −1.5 pts |
| RF-10 | Audit Issues | Financial Health | HIGH | −2.5 pts |
| RF-11 | Margin Risk | Financial Health | HIGH | −2.5 pts |
| RF-12 | Regulatory Overhang | Business Model | HIGH | −2.5 pts |
| RF-13 | Market Timing Risk | Market Position | MEDIUM | −1.5 pts |
| RF-14 | Capital Structure Risk | Financial Health | HIGH | −2.5 pts |
| RF-15 | Product Concentration | Business Model | MEDIUM | −1.5 pts |
| RF-16 | Geographic Concentration | Market Position | MEDIUM | −1.5 pts |
| RF-17 | Technology Obsolescence | Business Model | HIGH | −2.5 pts |
| RF-18 | Working Capital Stress | Financial Health | MEDIUM | −1.5 pts |
| RF-19 | Proceeds Quality | Mgmt & Governance | HIGH | −2.5 pts |
| RF-20 | Syndicate Spread Risk | Python post-hoc only | HIGH | −1.5/excess UW, cap −5.0 |
| RF-21 | PE/Sponsor Overhang | Mgmt & Governance | MEDIUM | −1.5 pts |
| RF-22 | Small Firm Suitability | (strong PASS signal) | HIGH | No numeric deduction |
| RF-23 | Insider Liquidity Overhang | Mgmt & Governance | MEDIUM | −1.5 pts |
| RF-24 | Auditor Quality Risk | Financial Health | MEDIUM | −1.5 pts |
| RF-25 | Accounting Quality Risk | FHR + BMQ both | HIGH | −2.5 pts each dimension |

**Detailed thresholds:**

- RF-01A: S-1 explicitly states IPO proceeds resolve the going concern; sole issue is pre-IPO capital deficiency. Set `going_concern_type: "capital_deficient"`, `going_concern: false`. Treatment: CONDITIONAL_HEAVY.
- RF-01B: Recurring losses / covenant violations / liquidity IPO proceeds cannot fix. If ambiguous between 01A and 01B, default to 01B. Set `going_concern: true`, `going_concern_type: "structural"`. AUTO PASS.
- RF-02: Top customer >40% = HIGH −2.5 from Market Position. Top customer >60% = CRITICAL −3.0 from Market Position.
- RF-03: A/R growing >1.5x faster than revenue; deferred revenue declining despite revenue growth; aggressive non-GAAP without justification.
- RF-04: Secondary shares >30% of offering; founders cashing out while running losses.
- RF-05: Post-IPO cash runway <18 months.
- RF-06: Dual-class with founder voting >70% post-IPO; no independent board majority; classified board.
- RF-07: Priced >3x sector median EV/Revenue with no growth/margin justification.
- RF-07A: EV/Revenue >50% above SIC-code-matched sector median.
- RF-07B: EV/EBITDA >25x on GAAP-loss + <30% YoY growth, OR EV/EBITDA >35x on any GAAP-loss company. Combined RF-07/07A/07B cap: max −7.5 total from Valuation.
- RF-08: CEO or CFO tenure <12 months; prior SEC enforcement; key-man without succession.
- RF-09: Material revenue from affiliates, loans to executives, above-market IP licensing.
- RF-10: Auditor change <24 months without reason; material weakness; non-Big 4 for >$100M revenue.
- RF-11: Gross margin <0% or <20% with no improvement path; declining margins at scale.
- RF-12: Active SEC investigation; DOJ inquiry; material litigation >$50M; adverse imminent regulation.
- RF-13: Filing in sector with recent failed IPOs; late-cycle sector.
- RF-14: PIK debt; high-yield aggressive covenants; convertibles with dilution >15%; Debt/EBITDA >5x.
- RF-15: >60% revenue from single product/service with no diversification roadmap.
- RF-16: >60% revenue from single geography with no expansion plan.
- RF-17: Core technology has near-term substitutes (AI disruption, open-source, consolidation).
- RF-18: Negative working capital or current ratio <1.0.
- RF-19: >30% of gross IPO proceeds to debt repayment, sponsor distributions, or existing shareholder liquidity. Calculate `total_non_operational_pct`.
- RF-20: >4 lead/co-manager underwriters on deal below $500M. Applied post-hoc by Python to `weighted_total` directly (−1.5 per excess UW over 4, capped at −5.0). NOT a dimension deduction — do not apply to any dimension score.
- RF-21: PE/sponsor ownership >40% post-IPO with lockup ≤180 days.
- RF-22: Offering <$50M, TTM revenue <$10M, or pre-revenue. Strong PASS signal, not automatic override.
- RF-23: Secondary shares >20% of total offering.
- RF-24: Not Big 4 or recognized mid-tier on deal >$50M. Big 4: Deloitte, EY, KPMG, PwC. Recognized mid-tier: RSM, Grant Thornton, BDO, Moss Adams, Crowe, Plante Moran, WithumSmith+Brown, Marcum, Cohen & Company.
- RF-25: `accounting_quality_score` ≤5. Deducts −2.5 from BOTH Financial Health AND Business Model Quality.

**Contradiction rule (hard requirement):**
If any red flag text uses language like "PASS-level trigger," "hard stop," "auto-PASS," or "not appropriate for our firm" — the `recommendation` field MUST be PASS. It is a critical logic error to write triggered flags with pass-level language and output UNDERWRITE or CONDITIONAL. Cross-check before finalizing every memo.

---

## 5. SCORING RULES

### 5a. Dimension Weights

```
weighted_total = (BMQ × 0.25) + (FHR × 0.15) + (MCP × 0.20) + (M&G × 0.20) + (VA × 0.20)
```

Each dimension is scored 0–10 AFTER applying RF deductions. `weighted_total` is on a 0–100 scale.

| Dimension | JSON Key | Base Weight | Leveraged Issuer Weight |
|---|---|---|---|
| Business Model Quality | `business_model_quality` | 25% | 25% |
| Financial Health & Runway | `financial_health_runway` | 15% | **20%** |
| Market & Competitive Position | `market_competitive_position` | 20% | 20% |
| Management & Governance | `management_governance` | 20% | 20% |
| Valuation Attractiveness | `valuation_attractiveness` | 20% | **15%** |

### 5b. Leveraged Issuer Detection (Python post-processing)

Computed automatically by `apply_leverage_adjustments()` after Claude returns JSON:
- GAAP-profitable + Debt/Adj.EBITDA >4x → `leveraged_issuer_flag: true`
- GAAP-loss + Debt/Adj.EBITDA >5x → `leveraged_issuer_flag: true`

When triggered: recalculates `weighted_total` with FHR 20% / VA 15% and appends
an adjustment note to `scores.adjustments[]`. App shows amber "LEVERAGED ISSUER" banner.

### 5c. Leverage Hard Floor (Python-enforced by `apply_leverage_floor()`)

- GAAP-profitable + Debt/EBITDA >4x: Financial Health score cannot exceed 4.0
- GAAP-loss + Debt/AdjEBITDA >6x AND interest expense >20% of revenue: FHR ≤4.0

### 5d. Governance Caps (Python-enforced by `apply_governance_cap()`)

Cap 1 — Extreme dual-class (ALL THREE conditions must be met):
  (a) vote ratio >10:1 between share classes
  (b) no time-based or market-cap-based sunset clause
  (c) founder/insider voting control >70% post-IPO
  → Management & Governance CANNOT score above 5.0. Set `management_governance_cap_reason: "extreme_dual_class"`.

Cap 2 — Independent board <50%: deduct 2.5 pts (HIGH). Separate from RF-06, accumulates.

Cap 3 — No lead independent director: deduct 1.5 pts (MEDIUM).

### 5e. RF Flag Deduction Amounts

- CRITICAL: AUTOMATIC PASS (RF-01B) or CONDITIONAL_HEAVY −4.0 pts (RF-01A)
- HIGH: −2.5 pts from affected dimension (exception: RF-01A is −4.0)
- MEDIUM: −1.5 pts from affected dimension
- LOW: −1.0 pt from affected dimension
- A dimension score cannot go below 0.0 regardless of total deductions.

### 5f. Scoring Floor Rule

If 3 or more HIGH or CRITICAL flags are triggered, `weighted_total` MUST be ≤64
(CONDITIONAL HEAVY or PASS) unless both BMQ and Market Position are ≥8.5.

### 5g. RF-01A / RF-01B Logic

- RF-01A (capital-deficient): Set `going_concern_type: "capital_deficient"`, `going_concern: false`.
  Deduct 4.0 pts from FHR. Treatment: CONDITIONAL_HEAVY minimum.
  If ambiguous, default to RF-01B.
- RF-01B (structural): Set `going_concern: true`, `going_concern_type: "structural"`.
  Python-enforced automatic PASS via `apply_scoring_adjustments()`.

### 5h. Python Post-Processing Pipeline Order

1. `enrich_valuation_with_live_comps()` — yfinance EV/Revenue for comp tickers
2. `enrich_with_damodaran()` — SIC → Damodaran industry mapping
3. `apply_scoring_adjustments()` — calls:
   - `apply_leverage_adjustments()` (leverage flag + weight recalc)
   - `apply_leverage_floor()` (FHR hard ceiling)
   - `apply_governance_cap()` (dual-class M&G cap)
   - RF-01B auto-PASS override
   - RF-20 post-hoc `weighted_total` adjustment

---

## 6. RECOMMENDATION THRESHOLDS

| Score | Band | JSON `recommendation` value | App badge |
|---|---|---|---|
| ≥75 | UNDERWRITE | `"UNDERWRITE"` | Green |
| 65–74 | CONDITIONAL LIGHT | `"CONDITIONAL_LIGHT"` | Amber |
| 55–64 | CONDITIONAL HEAVY | `"CONDITIONAL_HEAVY"` | Orange |
| <55 | PASS | `"PASS"` | Red |

Note: JSON uses underscores (`CONDITIONAL_LIGHT`). App displays with spaces via `.replace(/_/g, " ")`.

**Overrides:**
- RF-01A → minimum CONDITIONAL_HEAVY regardless of score
- RF-01B → AUTOMATIC PASS regardless of score (Python-enforced)
- RF-22 → strong PASS signal (not automatic)

**Section 03 rendering rules by recommendation:**
- UNDERWRITE: render §03 with enumerated `underwrite_reasons[]`
- CONDITIONAL (light or heavy): render §03C (amber left-border block) with numbered conditions from `conditional_underwrite_conditions[]`; no §03 header
- PASS: render §03 with enumerated `pass_reasons[]`

---

## 7. COMPARABLE IPO SELECTION — 6-CRITERION FRAMEWORK

Source: `ipo_screener.py` SYSTEM_PROMPT, lines ~280–340.

**Two hard filters (REQUIRED — cannot be waived):**

CRITERION 1 — INDUSTRY & BUSINESS MODEL:
  Must share same primary industry (anchored to SIC code) AND same core revenue model
  (SaaS, hardware, marketplace, services, manufacturing, etc.). Excluding semiconductor,
  hardware, REIT, or colocation companies as comps unless SIC and primary revenue model match.

CRITERION 2 — IPO SIZE / IMPLIED MARKET CAP:
  Historical IPO offering size and implied market cap at offer must be within 0.5x–2.0x of
  subject company's implied market cap at midpoint. A comp 5x larger or smaller is excluded.

**Four scored criteria (max 7 points):**

CRITERION 3 — GROWTH STAGE (0–2 pts):
  Same lifecycle stage (pre-profit high-growth / early-profit scaling / mature).
  2 pts: same stage. 1 pt: adjacent. 0 pts: different.

CRITERION 4 — REVENUE SCALE (0–2 pts):
  LTM revenue at IPO within same order of magnitude.
  2 pts: within 1.5x. 1 pt: within 3x. 0 pts: outside 3x.

CRITERION 5 — MARGIN PROFILE (0–2 pts):
  Gross margin at IPO within 15 pp of subject.
  2 pts: within 10 pp. 1 pt: within 15 pp. 0 pts: outside 15 pp.

CRITERION 6 — GEOGRAPHIC MIX (0–1 pt):
  Primary revenue geography matches (US-dominated vs. international-dominated).
  1 pt: match. 0 pts: different.

**Selection rule:**
- Hard filter first; any comp failing Criterion 1 or 2 is excluded automatically.
- Among survivors: minimum 4 of 7 points required to qualify.
- 6–7 pts → `primary_ipo_comp`
- 4–5 pts → `secondary_ipo_comp`
- <4 pts → excluded (never include)
- Output cap: maximum 5 comps (3 primary, 2 secondary). Never pad with weak comps.

**Required per comp:** company name, ticker, IPO date, offer price, first-day return %,
current vs. offer status, `comp_type` label, `comp_selection_rationale` (one sentence
citing which criteria met and where it scored lower).

---

## 8. PRE-ANALYSIS ELIGIBILITY GATE

Function: `validate_company_type(company_name, sic_code, filing_type)` in `analyze_filing()`.
Called in two passes before the S-1 is fetched.

**Abort conditions (any one triggers abort — no bypass):**

| Condition | Entity type |
|---|---|
| SIC 6770 | Blank Check Company |
| SIC 6726 | Investment Office (SPAC / Closed-End Fund / BDC) |
| SIC 6798 | REIT |
| Filing type S-11 | REIT registration |
| Filing type N-2 | Closed-End Fund / BDC |
| Name contains: "acquisition corp", "acquisition corporation", "blank check", "spac", "special purpose acquisition" | SPAC |
| Name contains: "royalty trust", "income trust", "investment trust" | Non-operating trust |
| Cover page contains "blank check company" or "no specific business plan" | SPAC (caught by `triage_filing()` after fetch) |

The gate prevents wasted tokens on ineligible filings. Do not add bypass flags or weaken
the gate. Non-operating entities are never eligible for ECM due diligence screening.

---

## 9. PRE-FETCH ENRICHMENTS (Python pipeline)

These run automatically in the Python pipeline after Claude returns JSON:

1. **Live comps (yfinance)** — `enrich_valuation_with_live_comps()`:
   Fetches EV/Revenue for Claude's comp tickers. Recalculates sector median and premium.
   Adds `live_comps_data[]` array to `valuation`. Requires `pip install yfinance`.
   Falls back gracefully if not installed.

2. **Damodaran benchmarks** — `enrich_with_damodaran()`:
   Maps company SIC code to Damodaran industry via `_SIC_DAMODARAN_MAP`.
   Populates `damodaran_comps.matched_industry`, `ev_ebitda_sector_median`, `ev_revenue_sector_median`.
   Source: NYU Stern January 2026 data.

3. **Scoring adjustments** — `apply_scoring_adjustments()`:
   Runs leverage detection, floor enforcement, governance caps, RF-01B auto-PASS,
   and RF-20 post-hoc `weighted_total` penalty. Rewrites `recommendation` if needed.
   Appends notes to `scores.adjustments[]`.

4. **Index validation** — `validate_memo_index(run_date)`:
   Verifies `_index.json` structure and `_manifest.json` entry. Auto-repairs if needed.
   Prints confirmation. MANDATORY — do not skip.

5. **PDF quality check** — `validate_pdf_output()`:
   Checks for empty sections, [object Object] risk, critical null fields, part divider
   targets. Prints warnings. MANDATORY — do not skip.

**When writing memos manually (outside the pipeline):**
You must manually update `_index.json` and `_manifest.json` after saving any memo JSON.
Run `validate_memo_index("YYYY-MM-DD")` afterward to confirm the memo appears in the dashboard.

---

## 10. CURRENT OPEN ISSUES AND PENDING FIXES

Three known bugs are tracked in `validateMemo()` in `ipo_screener_app.html`
(lines ~3291, ~3313, ~3328). The function logs structured `console.warn` messages
when these conditions are detected on memo load.

### Issue A: Cover Page Dimension Score Display

**Status:** Known bug, not yet fixed.
**Symptom:** Dimension score bars on the cover page may not display correctly.
**Location:** `renderMemo()` — dimension bars section, lines ~1620–1635.
**Root cause:** The dimension bar rendering calculates `v = d.val / 10` and then
`pct = v / 10 * 100` — this double-divides by 10. Dimension scores are stored on a
0–10 scale (e.g., `business_model_quality: 7.5`), so `v = 7.5 / 10 = 0.75` and
`pct = 0.75 / 10 * 100 = 7.5%` — a bar showing 7.5% instead of 75%.
**Fix needed:** In `dimBars` calculation, change `const v = d.val != null ? d.val / 10 : null`
and `const pct = v != null ? (v / 10 * 100).toFixed(0) + "%" : "0%"` so that pct is
`(d.val / 10 * 100)` directly. Also fix `d.val >= 7.5` comparisons to use raw dimension value.
**Note:** The score gauge (`weighted_total` 0–100) is correct. Only dimension bars are affected.

### Issue B: Public Comps JSON Rendering Bug (Section 08)

**Status:** Known bug, not yet fixed.
**Symptom:** Section 08 (Valuation Analysis) comps table shows raw text or is blank.
**Detected by:** `validateMemo()` check A at line ~3291:
  `"valuation.public_comps expected array but received string — likely raw JSON dump from Opus"`
**Root cause:** Claude sometimes returns `valuation.public_comps` as a JSON string
(stringified array) rather than a parsed array. The renderer cannot `.map()` over a string.
**Fix needed in renderer (Section 08 inline block in `renderMemo()`):**
  Before rendering comp rows, check if `val.public_comps || val.comparable_companies` is
  a string; if so, wrap with `JSON.parse()`. Use `safeRender()` per CLAUDE.md defensive rules.
**Fix needed in memo writing:**
  When writing memos manually, always ensure `valuation.comparable_companies` is an
  array of objects (not a string). Validate with `python3 -m json.tool`.

### Issue C: Accounting Practices Items Dashes Bug (Section 18)

**Status:** Known bug, not yet fixed.
**Symptom:** Section 18 (Accounting Practices) shows dashes in all rating cells.
**Detected by:** `validateMemo()` check B at line ~3313/3328:
  `"accounting category rows missing — accounting_practices.items[] has N entries but
  all risk_rating fields are null/empty"`
**Root cause:** Some older memos (and possibly new Claude output) populate the 8 accounting
dimensions as top-level named keys on `accounting_practices` (e.g., `accounting_practices.revenue_recognition`)
instead of inside `accounting_practices.items[]`. The `buildSection16()` renderer
handles both paths via fallback, but risk_rating badges only render for objects with
a `risk_rating` field — string values don't produce rating badges.
**Fix needed in renderer `buildSection16()` (line ~2680):**
  When falling back to named keys and the value is a string, infer risk_rating by
  keyword scan (Conservative / Standard / Aggressive / Highly Aggressive) from the string.
**Fix needed in memo writing:**
  Always populate `accounting_practices.items[]` as an array of 8 objects with `risk_rating`
  set to exactly one of: `Conservative`, `Standard`, `Aggressive`, `Highly Aggressive`.
  Do NOT use top-level named keys. The schema requires `items[]`.

---

## 11. STANDARD PROMPT FOR RUNNING A NEW MEMO

Use this exact workflow when asked to analyze a new S-1 filing:

### Step 1 — Fetch from EDGAR

```bash
# Find CIK from EDGAR submissions API
curl -s -A "IPO-Screener contact@regal.com" \
  "https://data.sec.gov/submissions/CIK{10-digit-padded}.json" | python3 -m json.tool | head -100

# Get filing index to find primary document filename
curl -s -A "IPO-Screener contact@regal.com" \
  "https://www.sec.gov/Archives/edgar/data/{CIK}/{accession-no-dashes}/" | grep -i "htm"

# Download the primary S-1/S-1A document
curl -s -A "IPO-Screener contact@regal.com" \
  "https://www.sec.gov/Archives/edgar/data/{CIK}/{accession-no-dashes}/{filename}.htm" \
  -o ~/IPO_Screener/raw_filings/{slug}.htm

# Extract text for analysis (handles HTML-stripped newline issues)
python3 -c "
from bs4 import BeautifulSoup
with open('raw_filings/{slug}.htm', encoding='utf-8', errors='ignore') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')
text = soup.get_text(separator='\n')
with open('raw_filings/{slug}_text.txt', 'w', encoding='utf-8') as f:
    f.write(text)
print(len(text), 'chars extracted')
"
```

### Step 2 — Check for S-1/A amendments

Always search for all versions (original S-1 plus any S-1/A amendments) and read all of them:
```bash
curl -s -A "IPO-Screener contact@regal.com" \
  "https://efts.sec.gov/LATEST/search-index?q=%22Company+Name%22&dateRange=custom&startdt=2026-01-01&enddt=2026-05-01&forms=S-1,S-1%2FA" | python3 -m json.tool
```

### Step 3 — Read and analyze the filing

Navigate the text using character offsets:
```bash
python3 -c "
with open('raw_filings/{slug}_text.txt', encoding='utf-8') as f:
    text = f.read()
# Find key sections
for section in ['Use of Proceeds', 'Risk Factors', 'Management', 'Underwriting', 'Financial Statements']:
    idx = text.find(section)
    print(f'{section}: char {idx}')
"
# Then read specific ranges:
python3 -c "
with open('raw_filings/{slug}_text.txt') as f: t = f.read()
print(t[START:END])
" | head -200
```

### Step 4 — Apply all analysis rules

Before writing the memo, cross-check:
1. Count all underwriters — if >4 on sub-$500M deal, RF-20 triggers
2. Check going concern language — is it 01A (capital-deficient) or 01B (structural)?
3. Calculate `total_non_operational_pct` for RF-19
4. Check top customer concentration for RF-02
5. Calculate EV = (midpoint share price × diluted post-IPO shares) − net cash post-IPO
6. Compute EV/Revenue and EV/EBITDA multiples
7. Check CEO/CFO tenure, board independence, dual-class structure
8. Count triggered HIGH/CRITICAL flags — if ≥3, floor weighted_total ≤64
9. Cross-check: any flag using PASS-level language → recommendation must be PASS
10. Populate all 8 accounting_practices.items[] with risk_rating

### Step 5 — Write the memo

```bash
# Write the JSON memo
# Validate JSON syntax
python3 -m json.tool ~/IPO_Screener/memos/{YYYY-MM-DD}/{slug}.json > /dev/null

# Update _index.json and _manifest.json
# Verify memo appears in dashboard
```

### Step 6 — Git backup

```bash
cd ~/IPO_Screener && git add -A && git commit -m "add {company} memo {YYYY-MM-DD}" && git push
```

---

## 12. EXISTING MEMOS INVENTORY

| Company | Date | Rec | Score | Notes |
|---|---|---|---|---|
| Novacyte Therapeutics | 2026-02-24 | UNDERWRITE | — | Earliest memo |
| Cybriatech Inc. | 2026-02-27 | PASS | — | |
| Encore Medical Inc. | 2026-03-03 | PASS | — | |
| Cortigent Inc. | 2026-03-05 | PASS | 46 | |
| Lendbuzz Inc. | 2026-03-09 | TBD | TBD | |
| (multiple others) | 2026-03 thru 2026-04 | varies | varies | See _manifest.json |
| Rare Earths Americas Inc. | 2026-04-28 | varies | varies | |
| HawkEye 360, Inc. | 2026-05-01 | PASS | 63 | RF-20 CRITICAL (9 UW on $400M); S-1/A No. 2; SIGINT/defense tech |

Full manifest at: `~/IPO_Screener/memos/_manifest.json`

---

## 13. KEY ARCHITECTURAL NOTES

### Writing Rules (apply to every memo field)
- `deal_committee_narrative` and all narrative fields reflect ONLY the current analysis.
  Never reference prior memos, prior scores, "corrections," or "overcredited" items.
- `executive_summary` and `amendment_changes_summary` follow the same rule.
- `amendment_changes_summary` is stored in JSON for internal record only — NEVER rendered
  in the app or PDF. Amendment banner shows only the date label.
- Section 03/03C rendering is mutually exclusive (PASS/UNDERWRITE vs. CONDITIONAL).

### CLAUDE.md HARD-STOP RULES (from MEMORY.md — non-negotiable)
1. **RF-19 HARD STOP:** >40% proceeds to non-operational use = PASS (50% is a PASS, full stop).
2. **RF-20 HARD STOP (SMALL FIRM):** >8 underwriters on sub-$1B deal = PASS.
   (Note: CLAUDE.md says >4 on sub-$500M for RF-20 penalty; MEMORY.md says >8 on sub-$1B for automatic PASS. Both are enforced; MEMORY.md rule governs the PASS recommendation.)
3. **RF-PARENT DIVESTITURE QUALITY:** Parent IPO'ing a division with widening GAAP losses and no trade buyer = PASS.
4. **RF-STANDALONE FINANCIALS:** No standalone audited financials = FHR ≤3.0. Combined/carved-out ≠ standalone.
5. **VALUATION PROFITABILITY RULE:** Do not use EV/Revenue discount as a positive for GAAP-loss companies. >20x EV/Adj.EBITDA on GAAP-unprofitable = `valuation_flag: true` and VA ≤4.0.
6. **SCORING FLOOR:** 3+ hard-stop flags → weighted_total ≤55 (PASS territory) regardless of business model score.
7. **FLAGS MUST DRIVE RECOMMENDATION:** Any flag text using pass-level language → recommendation = PASS. No contradictions.

### Defensive Rendering Layer
Three global helpers in the HELPERS section of `ipo_screener_app.html`:
- `safeRender(value, opts)` — converts any value to display-safe string. Use for all narrative fields.
- `missingDataFlag(sectionLabel)` — returns amber warning div when section has no data.
- `validateMemo(memo)` — called in `selectCompany()` before `renderMemo()`. Do not remove.

### RF Banner Rule
RF-style alert banners belong EXCLUSIVELY in Section 04. Section renderers §10–§17 must
NOT include rf-banner divs. The rf25Banner in buildSection16 was removed — do not re-add.

### PDF Export Rules
- Section 04: 3-column table (Flag Name | Severity | Description); no RF codes; severity-sorted.
- Section 18: PDF shows ONLY Aggressive/Highly Aggressive items. Full table in browser.
- Cover page: REGAL SECURITIES top left, score gauge, dimension bars.
- `@media print` CSS hides sidebar and filing panel, shows memo only.

### File Naming
Slugs use `_company_slug()`: lowercase, spaces to underscores.
Example: "HawkEye 360, Inc." → `hawkeye_360_inc.json`
Slug must match in `save_memo()` and `_index.json` `file` field.

### Amendment Handling
- `form_type == "S-1/A"` triggers prior memo lookup by slug match via `find_prior_memo()`.
- Prior memo summary injected into Claude prompt as context.
- New fields: `is_amendment: true`, `prior_memo_date: "YYYY-MM-DD"`, `amendment_changes_summary`.
- App shows "AMD" chip in filing list + blue amendment banner in viewer.

### Forward-Only Rule
Never regenerate or backfill existing memos. All schema changes are forward-only.
Renderers must gracefully handle missing fields on older memos (display "—", hide element).
Do not offer to backfill as part of any implementation.

### GitHub Push Rule
Every implementation ends with:
```bash
cd ~/IPO_Screener && git add -A && git commit -m '<descriptive message>' && git push
```
Auto-backup rule: After any session modifying `ipo_screener.py`, `ipo_screener_app.html`,
`fetch_only.py`, or `save_memos.py`, run auto-backup without asking for confirmation.
`memos/` is excluded by `.gitignore`.
