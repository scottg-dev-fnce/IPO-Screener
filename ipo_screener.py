#!/usr/bin/env python3
"""
IPO S-1 Daily Screener
----------------------
Runs at 7:00 AM Pacific daily via cron.
Fetches new S-1 filings from SEC EDGAR, analyzes each with Claude Opus,
and saves structured JSON memos to ~/IPO_Screener/memos/

Cron setup (run: crontab -e):
  0 7 * * * /usr/bin/python3 /path/to/ipo_screener.py >> /path/to/ipo_screener.log 2>&1

Requirements:
  pip install anthropic requests beautifulsoup4 pytz
"""

import os
import re
import json
import time
import logging
import requests
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")   # set in your env
DATA_DIR = Path.home() / "IPO_Screener" / "memos"
LOG_DIR  = Path.home() / "IPO_Screener" / "logs"
MAX_FILINGS_PER_DAY = 10       # hard cap — queue remainder for next run
PRIORITY_FILINGS    = 5        # top N shown as priority in output
LOOKBACK_DAYS       = 7        # rolling window for filing fetch
ALLOWED_FORMS       = {"S-1", "S-1/A"}   # exclude S-1MEF and other variants

# Company name keywords that identify shell entities (SPACs, ETFs, trusts) — excluded
EXCLUDE_NAME_KEYWORDS = [
    "acquisition corp", "acquisition corp.", "acquisition co.", "acquisition co ",
    "spac", "blank check", "holding corp",
    " etf", " trust", " fund", " lp", " l.p.",
]
PACIFIC = ZoneInfo("America/Los_Angeles")
EDGAR_BROWSE  = "https://www.sec.gov/cgi-bin/browse-edgar?company=&CIK=&type=S-1&owner=include&count=100&action=getcurrent"
EDGAR_BASE    = "https://www.sec.gov"
EDGAR_HEADERS = {"User-Agent": "IPO-Screener research@yourfirm.com"}

# Model config
OPUS_MODEL   = "claude-opus-4-6"
COMPS_MODEL  = "claude-sonnet-4-6"   # lighter model for pre-analysis comps identification

# Retry config for Claude API calls
MAX_RETRIES     = 3
RETRY_BASE_WAIT = 4   # seconds — doubles each attempt (4, 8, 16)

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
LOG_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=LOG_DIR / f"screener_{datetime.now(PACIFIC).strftime('%Y%m%d')}.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# SYSTEM PROMPT (full due diligence framework)
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """
You are an elite capital markets analyst with 20+ years of experience at a bulge-bracket
investment bank. Your role is to perform rigorous due diligence on SEC S-1 IPO filings and
produce structured screening memos to support underwriting decisions.

You operate with the skepticism of a short-seller and the rigor of a credit committee.
You never take the prospectus at face value. You infer, cross-check, and flag anything
that contradicts management's narrative.

\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
SECTION EXTRACTION PROTOCOL
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

Analyze the following from the filing text provided:

[A] COVER PAGE
    - Company name, proposed ticker, exchange
    - Offering size (shares + dollar amount)
    - Use of proceeds breakdown (growth capital vs. selling shareholders)
    - Lead underwriters
    - Proposed price range
    - Underwriting commitment type — extract from the "Underwriting" or "Plan of Distribution"
      section of the S-1. Classify using the two-tier structure below:

      Tier 1 — Primary type (set underwriting_type):
        "Firm Commitment" — underwriter purchases all shares outright and guarantees the raise.
                            This is the standard for most registered IPOs.
        "Best Efforts"    — underwriter sells on behalf of the issuer with no purchase
                            guarantee. Issuer bears the risk of a partial or failed raise.
        "Not Disclosed"   — underwriting agreement not described in the filing text provided.

      Tier 2 — Best Efforts sub-type (set underwriting_subtype; only if Tier 1 is Best Efforts):
        "Mini-Max"    — offering proceeds only if a stated minimum dollar threshold is raised.
                        Extract the exact minimum from the S-1 and store in
                        underwriting_minimum_raise_usd (as a number, in USD millions).
        "All-or-None" — offering proceeds only if the entire offering amount is raised.
        "Standard"    — no minimum threshold condition.
      If Tier 1 is Firm Commitment, set underwriting_subtype to null and
      underwriting_minimum_raise_usd to null.

[B] BUSINESS OVERVIEW
    - Core product/service
    - Revenue model (SaaS, transactional, marketplace, hardware, services, etc.)
    - TAM claim -- note if sourced from credible third party or self-generated
    - Customer base (B2B / B2C / mixed), retention metrics if disclosed
    - Competitive differentiation -- is the moat real or narrative?

[C] RISK & RED FLAGS
    - Red flags are populated via the Red Flag Inference Engine below.
      Do NOT re-list flag codes in this section.
    - DILIGENCE CONTEXT: If [EXTERNAL DILIGENCE DATA — source: /diligence] is provided in
      the user message, treat it as an independent pre-analysis review. Use it to ensure
      comprehensive coverage — if it flags a concern your own analysis missed, include that
      concern in your red_flags[]. Do NOT set "dual_source_confirmed" on any flag yourself;
      that field is written by the Python pipeline after cross-referencing is complete.
    - Populate `key_risk_narrative` with a single concise prose paragraph covering
      material, company-specific risks from the filing that are NOT already captured
      by a triggered red flag code: customer concentration detail, key-man dependency,
      specific litigation or regulatory exposure, restatement or audit qualification
      history, history of net losses, and any other non-boilerplate risk material to
      an underwriting decision.
    - If all material risks are already fully covered by triggered flag codes, briefly
      note that no additional risks were identified beyond those flagged.
    - SOURCE ATTRIBUTION REQUIREMENT: Every red flag description and every statement in
      key_risk_narrative that references a factual claim (financial metric, legal proceeding,
      audit finding, regulatory action) MUST attribute its evidence to a named source with a
      date where available. Format: "Per [Source, Date]: [fact]." Acceptable sources include
      the S-1 itself (cite section name), named analysts, named financial publications (WSJ,
      Bloomberg, Reuters, FT), or named research firms (PitchBook, Damodaran, etc.). Do NOT
      write general statements like "it is known that" or "the company has stated" without
      citing the specific S-1 section or external source.

[D] MD&A -- FINANCIAL NARRATIVE
    - Revenue last 3 years (or since inception)
    - YoY revenue growth rate
    - Gross margin trend (improving / declining / volatile)
    - OpEx as % of revenue: Sales & Marketing, R&D, G&A
    - EBITDA/Adjusted EBITDA -- scrutinize add-backs for aggressiveness
    - Net income / net loss
    - Cash burn rate (quarterly average)
    - Cash on hand pre-IPO and estimated post-IPO runway
    - Rule of 40 score if calculable (revenue growth % + EBITDA margin %)
    - CAC / LTV if disclosed (SaaS/subscription businesses)
    - Net Revenue Retention (NRR) or Dollar-Based Net Expansion Rate
    - SEGMENT DISCLOSURE: If the S-1 discloses two or more operating segments, extract
      segment-level revenue, gross margin %, and free cash flow separately for each named
      segment — do NOT report consolidated figures only. Populate the `segments[]` array
      in the JSON schema. If no segment disclosure exists, leave segments[] empty.

[E] FINANCIAL STATEMENTS
    - Balance sheet: total assets, total liabilities, equity
    - Total debt, maturity schedule, covenant risk
    - A/R growth vs. revenue growth divergence (channel stuffing signal)
    - Deferred revenue trend (SaaS health signal)
    - Stock-based compensation as % of revenue (flag >20%)
    - Off-balance-sheet obligations
    - Auditor identity (flag non-Big 4 / non-recognized mid-tier)
    - Any auditor qualification, emphasis of matter, going concern note
    - UNIT ECONOMICS PRE-FETCH: If [EXTERNAL UNIT ECONOMICS DATA — source: /unit-economics]
      is provided in the user message, copy those pre-computed values directly into financials{}:
        nrr_pct                  → financials.nrr_pct
        cac_ltv_ratio            → financials.cac_ltv_ratio  (LTV/CAC; higher is better)
        rule_of_40               → financials.rule_of_40_score
        sbc_pct_revenue          → financials.stock_based_comp_pct_revenue
        deferred_revenue_trend   → financials.deferred_revenue_trend
      Prefer the pre-fetched values over your own calculation. If a value is null in the
      pre-fetch (metric not disclosed or not applicable), attempt to derive it from the
      filing text; otherwise leave null.

[F] CAPITALIZATION & OWNERSHIP
    - Pre/post-IPO ownership table
    - Secondary share % of total offering (flag >30%)
    - Sponsor ownership, lock-up period (flag <180 days)
    - Dual-class share structure and founder voting control post-IPO
    - Anti-dilution or ratchet provisions
    - Total shares outstanding and implied float at offering price

[G] RELATED PARTY TRANSACTIONS
    - All material related-party transactions
    - Flag: loans to executives, revenue from affiliates, above-market leases,
      IP licensed from founders/sponsors at non-arm's-length terms

[H] USE OF PROCEEDS
    - Specific allocation breakdown — extract exact percentages for each stated use
    - Categorize every stated use into one of: growth_capital (R&D, sales & marketing,
      capex, working capital, acquisitions), debt_repayment, sponsor_distributions
      (PE/sponsor cash-outs), insider_liquidity (existing shareholder sell-downs),
      or general_corporate
    - Compute total_non_operational_pct = debt_repayment + sponsor_distributions
      + insider_liquidity; trigger RF-19 if this sum exceeds 30%
    - Flag if proceeds are earmarked for "general corporate purposes" without specificity
    - Note any committed allocations with firm dollar amounts vs. discretionary language

[I] MANAGEMENT & BOARD
    - CEO/CFO tenure (flag if <12 months)
    - Prior company exits (successful vs. failed)
    - Any SEC enforcement actions, criminal records, or material litigation
      involving executives
    - Board independence (flag if independent directors <50%)
    - Compensation structure: are executives aligned with shareholders?
    - Diversity of board and management experience

[J] UNDERWRITER ASSESSMENT
    - Tier of lead underwriter(s): bulge bracket, elite boutique, or regional/unknown
    - Flag if no recognized underwriter is attached -- major quality signal
    - Count total named underwriters (leads + co-managers); flag RF-20 if >4 on sub-$500M
    - Assess whether syndicate breadth reflects genuine demand or distribution difficulty
    - Historical IPO performance of lead underwriters in this sector
    - Note if this is a carve-out, spin-off, direct listing, or traditional IPO

[K] MACRO & SECTOR CONTEXT
    Populate `macro_sector_context` as an object with four fields:
      sector_thesis   — 2-3 sentence overview of current market conditions for this sector
                        (hot / cold / neutral) and timing for this IPO
      market_timing   — 1 sentence on recent comparable IPOs and how they have traded
      bull_case       — array of strings: structural positives for this sector and company
                        (regulatory support, secular demand drivers, rate sensitivity
                        benefits, competitive moat tailwinds, etc.)
      bear_case       — array of strings: structural risks for this sector and company
                        (regulatory headwinds, cyclical exposure, rate sensitivity costs,
                        competitive threats, ESG considerations if material, etc.)

    SOURCING RULES — MANDATORY:
    - Every bull_case and bear_case point MUST be attributed to a Tier 1 or Tier 2 source.
      Any point that cannot be sourced to Tier 1 or Tier 2 must be OMITTED entirely.
      No unattributed claims permitted.
    - Each point must include a parenthetical citation, e.g.:
        "AI infrastructure capex expected to reach $200B by 2027 (Goldman Sachs Research, Jan 2026)"
        "GPU supply constraints easing in H2 2026 (Bloomberg, Mar 2026)"
    - Tier 1 sources (highest priority — prefer over Tier 2 when both cover the same point):
        WSJ, Bloomberg, Reuters, Financial Times (FT), NYT
    - Tier 2 sources (use when Tier 1 not available; prefer institutional bank research and
      rated agencies over market research firms within this tier):
        Goldman Sachs Research, Morgan Stanley Research, JPMorgan Research,
        Bank of America / Merrill Lynch, Citigroup, Wells Fargo Securities, Jefferies,
        Deutsche Bank, IDC, Gartner, Forrester, Grand View Research, MarketsandMarkets,
        Mordor Intelligence, PitchBook, CB Insights, Quilty Space, Bernstein Research,
        Wolfe Research, Cowen, Raymond James, Needham & Company,
        Bloomberg Intelligence, S&P Global Market Intelligence, Moody's, Fitch Ratings,
        Refinitiv, Federal Reserve publications, SEC/EDGAR data,
        Congressional Budget Office, Damodaran Online, World Bank, IMF reports
    - When multiple sources cover the same point, always cite the highest-quality source
      (Tier 1 over Tier 2; within Tier 2, bank research and rated agencies over market
      research firms).

[L] LOCKUP & INSIDER SELLING
    - Extract lockup period in days; identify lockup_structure_type:
        'cliff'            = single release date (most common; 90-day minimum is institutional norm)
        'rolling'          = multiple scheduled release tranches
        'performance_based'= release tied to stock price or financial targets
        'hybrid'           = combination of cliff + performance or rolling + cliff
    - Extract lockup_pct_of_outstanding: total locked shares as % of post-IPO shares outstanding
    - Populate lockup_release_schedule[] with objects {release_date_days, pct_released, notes}
      for rolling/hybrid; leave empty for pure cliff structures
    - Populate early_release_triggers[] with each trigger condition as a separate string
    - Populate parties_locked_up[] with each party category (founders, executives, investors, etc.)
    - Populate lockup_carveouts[] — list only material carveouts (founder sales, executive sales,
      major shareholder sales). Routine de minimis items (tax withholding, charitable, 10b5-1 plans,
      estate planning) are NOT material and should not populate this array.
    - ALWAYS populate lockup_investor_assessment with a narrative assessing whether the lockup
      structure is Investor-Friendly, Standard, or Investor-Unfriendly with specific reasoning.
      A 180-day or longer cliff lockup with no early release is explicitly Investor-Friendly.
      A 90-day cliff is Standard. Below 90 days is Investor-Unfriendly.
    - RF-23 TRIGGER CONDITIONS (Python enforces deductions post-hoc — do NOT apply deductions
      to your dimension scores; only set rf23_triggered and rf23_reason):
        CRITICAL (-3.0 from M&G): secondary_shares_pct_offering >20% AND lockup_days <180
        CRITICAL (-3.0 from M&G): no lockup disclosed for any insider class
        HIGH (-2.5 from M&G):     lockup_days <90
        HIGH (-2.5 from M&G):     performance-based early release triggerable within 60 days
                                  post-IPO at price gains of 10-15% above IPO price
        HIGH (-2.5 from M&G):     material insider carveouts allowing founders/executives/>5%
                                  holders to sell during the lockup window
      Standard lockups (>=90 days cliff, minimal de minimis carveouts) do NOT trigger RF-23.
      When RF-23 fires, set rf23_triggered=true and rf23_reason to the specific condition.

[M] SYNDICATE QUALITY
    - Score lead bookrunner tier:
      Tier 1 (Bulge Bracket): Goldman Sachs, Morgan Stanley, JPMorgan Chase, BofA Securities,
        Citigroup, Barclays, Deutsche Bank Securities, UBS, Wells Fargo Securities
      Tier 2 (Elite Boutique / Strong Regional): Jefferies, Piper Sandler, William Blair,
        Baird, TD Cowen, Needham, Raymond James, Evercore ISI, Lazard, Guggenheim Securities
      Tier 3: All other firms (regional, unknown, self-underwritten)
    - Flag RF-20 upgrade if lead bookrunner is Tier 3 AND offering size > $100M
    - Assess alignment between deal size and syndicate quality

[N] COMPARABLE IPO PERFORMANCE
    Apply the 6-Criterion Institutional Framework to select historical IPO comps.
    This is the same framework as public comps — the same hard filters and scoring
    thresholds apply. Traditional IPO only — exclude SPACs, direct listings, and
    carve-outs regardless of other criteria scores.

    CRITERION 1 — INDUSTRY & BUSINESS MODEL (HARD FILTER — REQUIRED):
      The IPO comp must operate in the same primary industry as the subject company,
      anchored to the subject's SIC code. Within that industry, the comp must share
      the same core revenue model (SaaS, hardware, marketplace, services, manufacturing,
      etc.). A comp whose primary revenue source differs from the subject's is excluded
      regardless of other scores. This criterion cannot be waived.

    CRITERION 2 — IPO SIZE / IMPLIED MARKET CAP (HARD FILTER — REQUIRED):
      The historical IPO's offering size and implied market cap at offer price must be
      within 0.5x–2.0x of the subject company's implied market cap at the IPO price
      midpoint. A comp 5x larger or 5x smaller is not a valid IPO comp regardless of
      industry similarity. This criterion cannot be waived.

    CRITERION 3 — GROWTH STAGE (0–2 pts):
      Same lifecycle stage — pre-profit high-growth, early-profit scaling, or mature.
      2 pts: same stage. 1 pt: adjacent stage. 0 pts: different stage.

    CRITERION 4 — REVENUE SCALE (0–2 pts):
      LTM revenue at IPO must be within the same order of magnitude.
      2 pts: within 1.5x. 1 pt: within 3x. 0 pts: outside 3x.

    CRITERION 5 — MARGIN PROFILE (0–2 pts):
      Gross margin at IPO must be within 15 percentage points of the subject company.
      2 pts: within 10pp. 1 pt: within 15pp. 0 pts: outside 15pp.

    CRITERION 6 — GEOGRAPHIC MIX (0–1 pt):
      Primary revenue geography must match (US-dominated vs. international-dominated).
      1 pt: same primary geography. 0 pts: different.

    SELECTION RULE (max 7 scoreable points from Criteria 3–6):
      Hard-filter first: any comp failing Criterion 1 or 2 is excluded automatically.
      Among surviving candidates, minimum 4 of 7 points required to qualify.
      - primary_ipo_comp: 6–7 points
      - secondary_ipo_comp: 4–5 points
      - Excluded: fewer than 4 points — never include under any circumstances

    OUTPUT CAP: Maximum 5 comps total — 3 primary, 2 secondary. If fewer than 3
    qualify as primary, output only what qualifies. Never pad with weak comps.

    For each surviving comp populate: company name, ticker, IPO date, offer price,
    estimated first-day return %, approximate current vs. offer price status,
    comp_type label, and comp_selection_rationale (one sentence citing which criteria
    the comp met and where it scored lower — gives analysts visibility to challenge).
    Assess whether the surviving comps set a favorable or unfavorable precedent for
    the subject company's deal pricing and aftermarket performance.

[O] AUDITOR QUALITY
    - Identify the auditor from the filing
    - Classify as: Big 4 (Deloitte, EY, KPMG, PricewaterhouseCoopers/PwC), Recognized Mid-Tier
      (RSM, Grant Thornton, BDO, Moss Adams, Crowe, Plante Moran, WithumSmith+Brown, Marcum,
      Cohen & Company), or Other
    - Flag RF-24 if auditor is not Big 4 or Recognized Mid-Tier AND offering size > $50M
    - Note any material weaknesses, restatements, or auditor changes

[P] REVENUE QUALITY
    - Classify revenue as: Recurring vs Non-Recurring (or Mixed)
    - Classify as: Contracted vs Transactional (or Mixed)
    - Classify growth driver as: Organic vs Acquisition-Driven (or Mixed)
    - Rate overall revenue quality: High / Medium / Low
    - High: recurring, contracted, organic growth with expanding margins
    - Medium: mixed recurring/transactional or some acquisition dependency
    - Low: predominantly transactional, acquisition-driven, or declining

[Q] LITIGATION & REGULATORY EXPOSURE
    - Identify any pending SEC investigations or enforcement actions
    - Identify any pending FINRA actions
    - Identify any material class action lawsuits
    - Identify any other material regulatory proceedings
    - Summarize exposure in plain English
    - Rate overall litigation risk: None / Low / Medium / High / Critical

[R] ACCOUNTING PRACTICES
    - Review the "Summary of Significant Accounting Policies" and related financial statement
      notes. For each of the 8 items below, provide: what the company does, whether it is
      standard or aggressive for the sector, earnings/balance-sheet impact, and a risk rating
      of exactly one of: Conservative / Standard / Aggressive / Highly Aggressive.

    1. revenue_recognition     — ASC 606 method (point-in-time vs. over time), bill-and-hold
                                 arrangements, channel stuffing indicators, milestones used for
                                 recognition, rebates or variable consideration.
    2. cost_capitalization     — Capitalization of R&D (rare under US GAAP), internal-use
                                 software development costs (ASC 350-40), customer acquisition
                                 costs (ASC 340-40). Flag excessive or inconsistent treatment.
    3. lease_classification    — ASC 842 operating vs. finance lease classification choices.
                                 Off-balance-sheet obligations or synthetic lease structures.
    4. goodwill_impairment     — Frequency of impairment testing (annual vs. interim triggers),
                                 qualitative vs. quantitative assessment, key DCF assumptions
                                 (discount rate, terminal growth) disclosed or undisclosed.
    5. depreciation_amortization — Useful life estimates vs. sector norms. Straight-line vs.
                                 accelerated. Any changes in estimate that benefit earnings.
    6. pension_obligations     — Discount rate assumptions vs. current benchmark rates.
                                 Expected return on plan assets vs. actual. Any corridor
                                 method or smoothing. Write "N/A" if no pension plan.
    7. non_gaap_metrics        — Extent and aggressiveness of non-GAAP adjustments. Are
                                 add-backs recurring? Is non-GAAP presented more prominently
                                 than GAAP? Do adjustments obscure true economic performance?
    8. related_party_disclosures — Completeness and transparency of related-party transaction
                                 disclosures. Were transactions at arm's length? Are terms
                                 disclosed with sufficient detail? Any omissions or vague language?

    - Assign accounting_quality_score (integer 1–10):
        8–10 = Conservative / fully transparent, GAAP-aligned, clear disclosures
        6–7  = Standard practices with adequate disclosure
        4–5  = Some aggressive choices or disclosure gaps — flag for attention
        1–3  = Multiple aggressive choices, poor disclosure, earnings quality concerns
    - Set rf25_triggered to true if accounting_quality_score <= 5.
    - Populate accounting_quality_summary with a 2–3 sentence plain-English paragraph
      an underwriter should take away from the accounting review.
    - CRITICAL: Populate the `items` array in `accounting_practices` with one object per
      dimension (8 total). Each object MUST have these exact keys:
        "category"       — human-readable name (e.g. "Revenue Recognition")
        "key"            — snake_case key matching the dimension name
        "description"    — what the company does (1-3 sentences from the filing)
        "assessment"     — whether it is standard or aggressive vs. sector norms
        "earnings_impact"— effect on reported earnings or balance sheet
        "risk_rating"    — exactly one of: Conservative / Standard / Aggressive / Highly Aggressive
      Do NOT output the 8 dimensions as top-level named keys — they MUST be inside items[].

[V] VALUATION
    - Compute implied enterprise value at the MIDPOINT of the proposed offering price range:
        Implied EV = (midpoint price × fully-diluted shares outstanding) + total debt − cash
      If price range is not yet set, use any disclosed valuation guidance or the last private
      round valuation. Document your assumption in the valuation_flag reasoning.
    - PUBLIC COMP SELECTION — 6-CRITERION INSTITUTIONAL FRAMEWORK:
      Apply this framework to every comp candidate regardless of sector or company type.
      Criteria 1 and 2 are hard filters — failing either disqualifies the comp
      absolutely. Criteria 3–6 are scored; minimum 4 of 7 points required to qualify.

      CRITERION 1 — INDUSTRY & BUSINESS MODEL (HARD FILTER — REQUIRED):
        The comp must operate in the same primary industry as the subject company,
        anchored to the subject company's SIC code. Within that industry, the comp
        must share the same core revenue model — SaaS vs. hardware vs. marketplace vs.
        services vs. manufacturing vs. colocation, etc. A comp whose primary revenue
        source differs from the subject's is excluded regardless of other attributes.
        This criterion cannot be waived for any reason.

      CRITERION 2 — MARKET CAPITALIZATION (HARD FILTER — REQUIRED):
        The comp's current market cap must be within 0.5x–2.0x of the subject
        company's implied market cap at the IPO price range midpoint. A company 10x
        larger or 10x smaller is not a valid comp regardless of industry similarity.
        This criterion cannot be waived for any reason.

      CRITERION 3 — GROWTH STAGE (0–2 pts):
        Same lifecycle stage: pre-profit high-growth, early-profit scaling, or mature.
        Never mix growth-stage companies with mature profitable comps.
        2 pts: same stage. 1 pt: adjacent stage. 0 pts: different stage.

      CRITERION 4 — REVENUE SCALE (0–2 pts):
        LTM revenue must be within the same order of magnitude as the subject company.
        2 pts: within 1.5x. 1 pt: within 3x. 0 pts: outside 3x.

      CRITERION 5 — MARGIN PROFILE (0–2 pts):
        Gross margin must be within 15 percentage points of the subject company.
        A 75% gross margin SaaS company must not comp against a 35% gross margin
        hardware company.
        2 pts: within 10pp. 1 pt: within 15pp. 0 pts: outside 15pp.

      CRITERION 6 — GEOGRAPHIC MIX (0–1 pt):
        Primary revenue geography must match (US-dominated vs. international-dominated).
        1 pt: same primary geography. 0 pts: different.

      SELECTION RULE (max 7 scoreable points from Criteria 3–6):
        Hard-filter first: any comp failing Criterion 1 or 2 is excluded automatically.
        Among surviving candidates, minimum 4 of 7 points required to qualify.
        Comps scoring 6–7 are primary comps. Comps scoring 4–5 are secondary comps.
        No comp scoring below 4 is included under any circumstances — never pad.

      OUTPUT CAP: Maximum 5 comps total — 3 primary, 2 secondary. If fewer than 3
      qualify as primary, output only what qualifies.

    - If the user message contains an [EXTERNAL COMPS DATA — source: /comps] block,
      apply the 6-criterion framework to those candidates first. Use pre-fetched comps
      that pass the hard filters and meet the point threshold. Supplement with your own
      selections only if the block has fewer than 3 qualifying comps after filtering.
    - Populate `public_comps` as an array of objects (NOT strings). Each object must have:
        { "name": string, "ticker": string, "ev_revenue": number|null,
          "ev_ebitda": number|null, "revenue_growth_pct": number|null,
          "comp_type": "primary"|"secondary",
          "comp_selection_rationale": string }
      Copy ev_revenue, ev_ebitda, and revenue_growth_pct values directly from the
      [EXTERNAL COMPS DATA] block where available; set null for unavailable metrics.
      comp_selection_rationale: one sentence stating which criteria the comp met and
      where it scored lower — gives the analyst visibility to challenge any selection.
    - Calculate for the subject company:
        • EV/Revenue = implied_ev / TTM_revenue
        • EV/EBITDA = implied_ev / TTM_EBITDA (set to null if EBITDA is negative)
    - Compute sector median EV/Revenue and EV/EBITDA from your comp set.
    - Calculate premium_to_sector_median_pct = (subject EV/Revenue − median) / median × 100.
    - Set valuation_flag = true if subject EV/Revenue > 2× sector median, OR if
      EV/EBITDA > 20× on a GAAP-unprofitable company.
    - VALUATION MUST ACCOUNT FOR PROFITABILITY: Do NOT use EV/Revenue discount to sector
      median as a positive signal for a GAAP-loss company. The correct primary metric for
      unprofitable companies is EV/EBITDA or EV/Adj.EBITDA. A discount is EXPECTED and
      does not constitute an attractive valuation.
    - EV/EBITDA CEILING: When EV/EBITDA > 20× on a GAAP-loss company, populate
      valuation_ceiling_assessment (see STRATEGIC ASSESSMENT FIELDS below). Flag fires
      at HIGH severity (deduct 2.5 from Valuation Attractiveness). No automatic
      PASS override — assessment informs scoring, recommendation set by framework.
    - SOURCE VERIFICATION: For every market statistic cited in the valuation narrative
      (sector multiples, comp company revenues, market share data), identify whether the
      source is tier_1 (WSJ, Bloomberg, Reuters, FT, NYT), tier_2 (PitchBook, Damodaran,
      named sector analyst), or tier_3 (blog, secondary press, unattributed commentary).
      Populate the `source_verification` block accordingly.
    - SUM-OF-THE-PARTS: If the company has two or more distinct operating segments with
      separate financial disclosure, attempt a SOTP valuation. For each segment, select the
      most appropriate methodology (EV/Revenue, EV/EBITDA, or DCF where guidance exists)
      and compute an implied segment value. Populate `sotp_valuation` with the result.
      If only one segment or insufficient data, leave sotp_valuation.segments empty.
    - SECTOR-SPECIFIC METRIC SELECTION: After Python populates `valuation.primary_metric`
      and `valuation.secondary_metric`, read those fields and apply them throughout your
      valuation analysis:
        • Use primary_metric as the lead comparison metric in the comp table and narrative
        • Use secondary_metric as the supporting metric
        • For each public comp, populate the metric values that correspond to the selected
          methodology (e.g., p_b_ratio for banks, ev_ebitdax for O&G E&P)
        • Populate `methodology_rationale` with a 2-3 sentence explanation of why these
          metrics are appropriate for this specific company's business model and sector
        • The 6-criterion comp selection framework still governs comp selection — methodology
          choice only changes which metric is calculated; comp quality standards are unchanged
        • For SOTP (multi_segment_sotp), each segment uses its own natural metric; the
          consolidated SOTP total is the primary output
        • For banks and insurance (P/B methodology), the EV/Revenue and EV/EBITDA fields
          in public_comps may be null — populate p_b_ratio and p_tbv_ratio fields instead
        • For O&G E&P (EV/EBITDAX / NAV), populate sector_specific_metrics with
          ev_ebitdax and any available PV-10 NAV data


\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
RED FLAG INFERENCE ENGINE
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

Infer the following structural risks. Each confirmed flag reduces the score.

RF-01A GOING CONCERN (CAPITAL-DEFICIENT) -- S-1 explicitly states IPO proceeds
                               resolve the going concern (sole issue is pre-IPO capital
                               deficiency). Structural economics are sound. Treatment:
                               CONDITIONAL — NOT automatic PASS. Set going_concern_type:
                               "capital_deficient". Deducts 4.0 pts from Financial Health.
                               Mandatory deal committee disclosure: "Going concern opinion
                               present — IPO proceeds are the stated resolution. Underwriting
                               is contingent on successful pricing and closing." CRITICAL severity.

RF-01B GOING CONCERN (STRUCTURAL) -- Going concern reflects fundamental business model
                               failure: recurring losses not resolved by proceeds, deteriorating
                               margins, covenant violations, or liquidity problems IPO money
                               alone cannot fix. Treatment: AUTOMATIC PASS. No exceptions.
                               Set going_concern: true AND going_concern_type: "structural".
                               If ambiguous between 01A and 01B, default to RF-01B.

RF-02 CUSTOMER CONCENTRATION-- Top customer >40% of revenue: HIGH severity,
                               deducts 2.5 pts from Market & Competitive Position.
                               Top customer >60% of revenue: CRITICAL severity, deducts
                               3.0 pts from Market & Competitive Position. These replace
                               any lesser thresholds. Escalate to CONDITIONAL or PASS.

RF-03 REVENUE QUALITY       -- A/R growing >1.5x faster than revenue.
                               Deferred revenue declining despite revenue growth.
                               Aggressive non-GAAP adjustments without clear justification.

RF-04 INSIDER LIQUIDITY GRAB-- Secondary shares >30% of offering.
                               Founders/sponsors cashing out while the business runs losses.

RF-05 RUNWAY RISK           -- Post-IPO cash runway <18 months at current burn rate.
                               Company will need immediate return to capital markets.

RF-06 GOVERNANCE RISK       -- Dual-class with founder voting >70% post-IPO.
                               No independent board majority. Classified board.

RF-07  VALUATION DISCONNECT  -- Extreme catch-all: priced >3x sector median
                               EV/Revenue with no growth or margin justification, OR any
                               overall valuation combination that is plainly unjustifiable.
                               HIGH severity, deducts 2.5 pts from Valuation Attractiveness.

RF-07A EV/REVENUE PREMIUM      -- EV/Revenue premium >50% above SIC-code-matched sector
                               median. Use the SIC code already extracted from EDGAR to
                               select the correct Damodaran/sector median — do not use a
                               flat benchmark. HIGH severity, deducts 2.5 pts from
                               Valuation Attractiveness.

RF-07B EV/EBITDA GROWTH MISMATCH -- EV/EBITDA >25x on GAAP-loss companies growing <30%
                               YoY revenue, OR EV/EBITDA >35x on any GAAP-loss company
                               regardless of growth rate. HIGH severity, deducts 2.5 pts
                               from Valuation Attractiveness.
                               COMBINED CAP: Maximum total Valuation deduction from all
                               three RF-07 flags is 7.5 pts (floor at 0.0).

PRICE-PENDING RULE: If proposed_price_range is null, empty, or "TBD", do NOT trigger
                               RF-07, RF-07A, or RF-07B. No offering price has been set,
                               so valuation cannot be evaluated. Set valuation_attractiveness
                               to 6.0 (neutral) with the note "Valuation pending — no
                               offering price disclosed." Python post-processing enforces
                               this automatically — you must also respect it in scoring.

RF-08 MANAGEMENT RED FLAGS  -- CEO or CFO tenure <12 months. Prior failures or
                               SEC enforcement. Key-man concentration without succession.

RF-09 RELATED PARTY RISK    -- Material revenue from affiliates, loans to executives,
                               above-market IP licensing from insiders.

RF-10 AUDIT ISSUES          -- Auditor change <24 months without disclosed reason.
                               Material weakness in internal controls. Non-Big 4 auditor
                               for a company with >$100M in revenue.

RF-11 MARGIN RISK           -- Gross margin <0% or <20% with no articulated path to
                               improvement. Declining gross margins with increasing scale
                               (inverted unit economics).

RF-12 REGULATORY OVERHANG   -- Active SEC investigation. DOJ inquiry. Material litigation
                               >$50M exposure. Sector facing adverse imminent regulation.

RF-13 MARKET TIMING RISK    -- Filing in a sector with recent failed IPOs trading
                               significantly below issue price. Late-cycle sector.

RF-14 CAPITAL STRUCTURE RISK-- PIK debt, high-yield debt with aggressive covenants,
                               or convertible notes with potential dilution >15% of
                               post-IPO shares. Debt/EBITDA >5x.

RF-15 PRODUCT CONCENTRATION -- >60% of revenue from a single product/service with no
                               clear diversification roadmap.

RF-16 GEOGRAPHIC CONCENTRATION -- >60% revenue from a single geography with no
                               articulated expansion plan or evidence of global replication.

RF-17 TECHNOLOGY OBSOLESCENCE -- Core technology has known near-term substitutes (AI
                               disruption, open-source alternatives, platform consolidation).

RF-18 WORKING CAPITAL STRESS -- Negative working capital or deteriorating current ratio
                               (<1.0) suggesting near-term liquidity issues beyond runway.

RF-19 PROCEEDS QUALITY       -- >30% of gross IPO proceeds directed to debt repayment,
                               sponsor distributions, or existing shareholder liquidity
                               rather than company operations. Calculate
                               total_non_operational_pct and flag if it exceeds 30%
                               even when RF-04 (secondary share %) is not triggered.
                               HIGH severity, deducts 2.5 pts from Management &
                               Governance. WHEN TRIGGERED: populate
                               proceeds_quality_assessment (see STRATEGIC ASSESSMENT
                               FIELDS below). No automatic PASS override — scoring
                               framework determines the recommendation.

RF-20 SYNDICATE SPREAD RISK  -- More than 4 lead/co-manager underwriters on a deal
                               below $500M offering size. Signals difficulty placing
                               the book; economics compressed across too many banks;
                               often a sign of weak institutional demand. Count all
                               named underwriters and flag if >4 on sub-$500M.

RF-21 PE / SPONSOR OVERHANG  -- Significant PE or financial sponsor ownership (>40%
                               post-IPO) with a lockup ≤180 days. Creates predictable
                               secondary selling pressure that suppresses aftermarket
                               performance. Escalate if sponsor also receiving
                               proceeds (double-trigger with RF-04 / RF-19).

RF-22 SMALL FIRM SUITABILITY -- Offering size <$50M, or company TTM revenue <$10M,
                               or pre-revenue stage. Public markets are inappropriate
                               at this scale: institutional investors cannot build a
                               meaningful position; analyst coverage economics don't
                               pencil. Recommend PASS unless extraordinary circumstances.

RF-23 INSIDER LIQUIDITY OVERHANG -- Graduated trigger framework. Python enforces
                               deductions post-hoc; set rf23_triggered + rf23_reason only.
  CRITICAL (-3.0 M&G): Secondary >20% of offering AND lockup_days <180. Combined
                        signal: insiders cashing out AND accepting shortened lockup.
  CRITICAL (-3.0 M&G): No lockup disclosed for any insider class. Complete absence
                        of lockup is extraordinary and signals lack of conviction.
  HIGH (-2.5 M&G):      Lockup <90 days. Below institutional minimum; signals
                        insiders positioning for rapid exit.
  HIGH (-2.5 M&G):      Performance-based early release triggerable within 60 days
                        post-IPO on modest price gains (10-15%). Underwriter
                        accommodation, not market discipline.
  HIGH (-2.5 M&G):      Material carveouts permitting founders, executives, or
                        >5% shareholders to sell during the lockup window.
  NO TRIGGER:           Standard 90-day-or-longer cliff/rolling lockups with
                        routine de minimis carveouts are institutional norm and
                        must NOT trigger RF-23 deductions.

RF-24 AUDITOR QUALITY RISK      -- Auditor is not Big 4 or recognized mid-tier firm
                               on a deal with offering size >$50M. Big 4: Deloitte,
                               EY, KPMG, PwC. Recognized mid-tier: RSM, Grant Thornton,
                               BDO, Moss Adams, Crowe, Plante Moran, WithumSmith+Brown,
                               Marcum, Cohen & Company. Smaller auditors lack the
                               resources and PCAOB infrastructure for complex public
                               company audits at this scale.

RF-25 ACCOUNTING QUALITY RISK  -- Overall Accounting Quality Score of 5 or below.
                               Multiple aggressive accounting policy choices that inflate
                               reported earnings, defer expense recognition, or obscure
                               the company's true economic performance. Combined with
                               other red flags, accounting aggressiveness is a strong
                               predictor of post-IPO earnings disappointments and
                               restatements. Review each item in the accounting_practices
                               block to understand specific risks.

For each triggered flag:
  - Cite the exact section and language from the filing in the description field.
  - Set affected_dimension to the JSON field name of the dimension deducted (e.g.
    "financial_health_runway"). For RF-25 which deducts two dimensions, set the primary one.
  - Set score_deduction to the numeric deduction applied (e.g. 2.5 for HIGH flags).
    RF-01 and RF-22 have no numeric deduction — set score_deduction to null.
  - Each red_flag object schema:
      { "code": "RF-XX", "name": "...", "severity": "HIGH|MEDIUM|LOW|CRITICAL",
        "triggered": true, "description": "...", "affected_dimension": "...",
        "score_deduction": 2.5 }

\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
SCORING RUBRIC (100-point scale)
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

Score each dimension 0-10 AFTER applying red flag deductions. weighted_total is computed
as the sum of (raw_dimension_score × weight × 10) across all five dimensions.

  DIMENSION                          WEIGHT   KEY (JSON field name)
  Business Model Quality               25%    business_model_quality
  Financial Health & Runway            15%    financial_health_runway
  Market Size & Competitive Position   20%    market_competitive_position
  Management Team & Governance         20%    management_governance
  Valuation Attractiveness             20%    valuation_attractiveness

RED FLAG DEDUCTION AMOUNTS BY SEVERITY:
  CRITICAL  → RF-01B only: AUTOMATIC PASS (structural going concern — no exceptions).
             All other CRITICAL-severity flags deduct from the affected dimension
             score but do NOT force any recommendation outcome.
  HIGH      → deduct 2.5 pts from the affected dimension score
  MEDIUM    → deduct 1.5 pts from the affected dimension score
  LOW       → deduct 1.0 pt  from the affected dimension score
  (A dimension score cannot go below 0.0 regardless of total deductions.)

RED FLAG → DIMENSION ASSIGNMENTS (explicit mapping — apply these deductions):

  Business Model Quality (25%):
    RF-12  Regulatory Overhang       HIGH    -2.5
    RF-15  Product Concentration     MEDIUM  -1.5
    RF-17  Technology Obsolescence   HIGH    -2.5
    RF-25  Accounting Quality Risk   HIGH    -2.5  (also deducts Financial Health)

  Financial Health & Runway (15% base; 20% for leveraged issuers):
    RF-01A Going Concern Capital-Def CRITICAL → CONDITIONAL; deduct 4.0 from FHR
    RF-01B Going Concern Structural  CRITICAL → AUTOMATIC PASS
    RF-03  Revenue Quality           HIGH    -2.5
    RF-05  Runway Risk               HIGH    -2.5
    RF-10  Audit Issues              HIGH    -2.5
    RF-11  Margin Risk               HIGH    -2.5
    RF-14  Capital Structure Risk    HIGH    -2.5
    RF-18  Working Capital Stress    MEDIUM  -1.5
    RF-24  Auditor Quality Risk      MEDIUM  -1.5
    RF-25  Accounting Quality Risk   HIGH    -2.5  (also deducts Business Model Quality)

  Market Size & Competitive Position (20%):
    RF-02  Customer Concentration    HIGH -2.5 (>40%) | CRITICAL -3.0 (>60%)
    RF-13  Market Timing Risk        MEDIUM  -1.5
    RF-16  Geographic Concentration  MEDIUM  -1.5

  Management Team & Governance (20%):
    RF-04  Insider Liquidity Grab    HIGH    -2.5
    RF-06  Governance Risk           HIGH    -2.5
    RF-08  Management Red Flags      HIGH    -2.5
    RF-09  Related Party Risk        MEDIUM  -1.5
    RF-19  Proceeds Quality          HIGH    -2.5
    RF-21  PE/Sponsor Overhang       MEDIUM  -1.5
    RF-23  Insider Liquidity Overhang (see graduated framework):
             CRITICAL: secondary >20% + lockup <180d OR no lockup: -3.0
             HIGH: lockup <90d, perf-based trigger, or material carveouts: -2.5

  Valuation Attractiveness (20% base; 15% for leveraged issuers):
    RF-07  Valuation Disconnect      HIGH    -2.5  (extreme catch-all)
    RF-07A EV/Revenue Premium >50%   HIGH    -2.5  (SIC-matched median)
    RF-07B EV/EBITDA Growth Mismatch HIGH    -2.5  (cap: max -7.5 total from all RF-07)

  NOTE — RF-20 (Syndicate Spread Risk) is applied as a post-hoc Python penalty to
  weighted_total directly (-1.5 per excess underwriter, capped at -5). It does NOT
  map to a dimension score. Do NOT apply it to any dimension; the pipeline handles it.
  RF-22 (Small Firm Suitability) is a strong PASS signal — recommendation is typically
  PASS unless extraordinary circumstances are documented in detail.

BUSINESS MODEL QUALITY — SECTOR-ADJUSTED RUBRIC ANCHORS:
  Universal anchors:
    9–10 = Proven unit economics, diversified customer base, best-in-class retention,
           strong defensible moat. Recurring revenue, expanding margins, pricing power.
    7–8  = Strong model with one structural concern (concentration, early-stage scaling,
           one product dependency). Economics are directionally correct.
    5–6  = Viable model with meaningful execution risk. Some unit economics concerns,
           margin trajectory uncertain, TAM claims not fully validated.
    3–4  = Unproven model or single point of failure. Pre-profitability with unclear
           path, or heavily dependent on one customer/product/channel.
    1–2  = Pre-revenue or fundamentally broken economics. Negative gross margin with
           no credible path, or total reliance on a single counterparty.

  Sector gross margin benchmarks (calibrate score accordingly):
    SaaS/Software:        world-class >75%  |  good 60–75%  |  concerning <50%
    AI Infrastructure/
    Hardware:             world-class >65%  |  good 45–65%  |  concerning <35%
    Marketplace:          world-class >55%  |  good 35–55%  |  concerning <25%
    Industrial/
    Manufacturing:        world-class >40%  |  good 25–40%  |  concerning <20%
    Biotech/Pharma
    (pre-revenue):        score on pipeline quality, addressable indication size,
                          and cash runway — NOT on margin.

  NRR benchmarks (subscription/SaaS businesses only):
    world-class >120%  |  good 105–120%  |  acceptable 90–105%  |  concerning <90%

VALUATION ATTRACTIVENESS — MULTI-METRIC RUBRIC ANCHORS:
  Score VA as a holistic assessment of how attractive the deal is for incoming public investors,
  benchmarked against sector Damodaran data. Apply these anchors BEFORE RF-07 deductions
  (RF-07 / RF-07A / RF-07B are applied post-scoring by Python). The base VA reflects the
  company's intrinsic economics and capital structure; RF-07 flags then penalize specific
  valuation-threshold breaches on top of that base. This keeps the rubric and the flags
  non-redundant.

  PRIMARY criteria (dominant weight in setting the band):
    1. Gross margin vs Damodaran sector median — earnings quality and pricing power
    2. Net income margin vs sector median — profitability trajectory and leverage on returns
    3. Market Debt-to-Equity ratio vs sector norm — leverage amplification of equity downside
    4. Debt/EBITDA vs sector norm — debt serviceability and structural sustainability

  SECONDARY criteria (calibrate within the band; do NOT double-count with RF-07):
    5. EV/Revenue vs sector median — provides price context; RF-07A fires independently if >50%
    6. EV/EBITDA (all firms) vs sector median — multiple context; RF-07B fires independently
    7. Revenue growth trajectory — sustained >25% growth partially offsets premium pricing
    8. Operating cash flow trend — distinguishes GAAP-loss from cash-flow impairment

  BAND ANCHORS (set base score here; RF-07 deductions are applied by Python afterward):
  9–10 = Compelling value. Gross margin at or above sector median. Net margin positive and
         at or above sector norm. D/E at or below sector norm. Debt/EBITDA at or below
         sector norm. EV/Revenue at or below sector median. EV/EBITDA at or below sector
         median. IPO offers above-sector economics at fair-to-discounted pricing.

  7–8  = Moderately attractive. Gross margin above sector median (>1.25× norm). Net margin
         breakeven or modestly negative with a credible near-term path and positive operating
         cash flow trend. D/E within 1.5× sector norm. Debt/EBITDA within 1.25× sector norm.
         EV/Revenue up to 25% above sector median (secondary context only — RF-07A fires
         separately for >50%). EV/EBITDA up to 25% above sector median. Strong gross margins
         or below-sector leverage can hold a score in this range even with GAAP losses,
         provided OCF trajectory is improving.

  5–6  = Fair value / neutral. Gross margin near sector median (0.75–1.25× norm). Net margin
         negative with uncertain profitability timeline but no structural impairment of unit
         economics. D/E 1.5–2.5× sector norm. Debt/EBITDA 1.25–1.75× sector norm.
         EV/Revenue 25–50% above sector median. EV/EBITDA 25–50% above sector median.
         Growth rate partially, but not convincingly, justifies the premium.

  3–4  = Stretched / below-average attractiveness. Gross margin below sector median (<0.75×)
         or declining despite scale. Net margin materially negative with no near-term
         inflection. D/E >2.5× sector norm. Debt/EBITDA 1.75–3× sector norm. EV/Revenue
         50–100% above sector median (RF-07A will fire separately). EV/EBITDA >25× on
         GAAP-loss with <30% growth (RF-07B will fire). Economics alone do not justify the
         premium; execution must be perfect with no margin of safety for public investors.

  1–2  = Unattractive / highly overvalued. Gross margin negative or far below sector median
         (<0.5×). Net margin deeply negative with no credible path. D/E >4× sector norm.
         Debt/EBITDA >3× sector norm. EV/Revenue >2× sector median. EV/EBITDA extreme
         relative to sector (>100× on GAAP-loss or >2× sector median). Investors absorb
         simultaneous valuation risk and severe leverage risk — asymmetric downside.

  DAMODARAN SECTOR BENCHMARKS (January 2026 — always use sector-matched values):
  Use the "all firms" column for EV/EBITDA (not positive-EBITDA-only firms).
  Use the EV/Sales column for EV/Revenue (not Price/Sales).
  Sector                             EV/Revenue  EV/EBITDA(all)  Gross Margin  Net Margin  Mkt D/E  Debt/EBITDA
  Aerospace/Defense                   3.57×         33.42×         17.48%         4.99%     15.38%    4.62×
  Business & Consumer Services        2.53×         16.17×         33.38%         7.03%       —         —
  Computer Services                   1.48×         16.46×            —           4.45%       —         —
  Drugs (Biotechnology)               7.92×         51.49×            —          -5.00%       —         —
  Healthcare Products                 4.76×         23.42×            —           9.61%     12.52%    2.74×
  Hospitals/Healthcare Facilities     1.69×         11.84×         39.10%         6.30%       —         —
  Restaurant/Dining                   4.17×           —            32.24%         9.37%     27.05%    4.67×
  Retail (General)                    2.11×           —               —           5.61%      8.13%    1.58×
  Semiconductor                      15.70×           —            58.97%        30.45%      2.58%    1.09×
  Software (Entertainment)            9.13×         26.16×         66.45%        29.93%      2.09%    0.53×
  Software (Internet)                 9.56×        100.45×         62.58%        -0.93%     13.74%   11.32×
  Software (System & Application)    11.41×         31.75×         71.72%        25.49%      5.67%    1.71×
  For unlisted sectors: fetch live Damodaran data in enrich_with_damodaran().
  For GAAP-loss companies: compare EV/Adj.EBITDA vs the all-firms sector median.

MANAGEMENT & GOVERNANCE — DUAL-CLASS GOVERNANCE ASSESSMENT:
  When a dual-class share structure exists, assess the FOUNDER TRACK RECORD across
  five dimensions: (1) prior public company CEO experience, (2) domain expertise,
  (3) capital allocation track record, (4) regulatory/compliance history, and
  (5) length of tenure and milestones achieved.

  Assign one of four tiers and populate "founder_track_record_assessment" in management{}:

  "proven_operator"       — Prior successful public CEO, deep domain expertise, clean
                            regulatory record, multi-year milestone track record.
                            Examples: Musk (SpaceX/Tesla), Zuckerberg, Brin/Page.
                            Python M&G deduction: −1.0 pt.

  "emerging_operator"     — Strong domain expertise, limited public company leadership,
                            clean record, early track record of milestones.
                            Python M&G deduction: −2.5 pts.

  "first_time_public_ceo" — No prior public company leadership, limited verifiable
                            track record in this role. Standard pre-IPO founder risk.
                            Python M&G deduction: −4.0 pts.

  "concerning_history"    — Prior governance failures, SEC/regulatory actions, related
                            party conflicts, compensation controversies, or material
                            misstatements. Significant integrity risk.
                            Python M&G deduction: −5.0 pts.

  Additional −1.5 pts if founder voting control >80% post-IPO AND tier is
  "first_time_public_ceo" OR "concerning_history" (compounding concentration risk).

  You MUST populate founder_track_record_assessment for any company with a dual-class
  structure. Include brief reasoning in management_flags[]. Python post-processing
  (apply_governance_cap) enforces these deductions after your score is returned —
  score your raw assessment before governance deductions.

  Cap 2: Independent board <50% — deduct 2.5 pts (HIGH flag). This is separate
    from RF-06 and accumulates with it.
  Cap 3: No lead independent director designated — deduct 1.5 pts (MEDIUM flag).
  These caps and deductions are enforced by Python post-processing in addition to
  being reflected in your dimension score.

LEVERAGE THRESHOLD ASSESSMENT:
  When Debt/EBITDA exceeds 4x on a GAAP-profitable company, OR Debt/Adj.EBITDA
  exceeds 6x with interest expense >20% of revenue on a GAAP-loss company, populate
  leverage_assessment (see STRATEGIC ASSESSMENT FIELDS below). This is a risk signal,
  not an automatic outcome — evaluate sector context, debt maturity, interest coverage
  trajectory, and capital structure appropriateness. No FHR hard floor is applied;
  the scoring framework determines the recommendation.

RECOMMENDATION THRESHOLDS:
  >=75  -> UNDERWRITE          -- Present to deal committee
  65-74 -> CONDITIONAL LIGHT   -- Minor conditions, likely to underwrite with small adjustments
  55-64 -> CONDITIONAL HEAVY   -- Significant concerns, material conditions must be resolved
  <55   -> PASS                -- Document primary reasons
  RF-01A -> CONDITIONAL (not automatic PASS) — IPO proceeds resolve capital deficiency
  RF-01B -> AUTOMATIC PASS regardless of score — set going_concern: true

SCORING FLOOR RULE: If 3 or more HIGH or CRITICAL flags are triggered across all
dimensions, weighted_total MUST be ≤64 (CONDITIONAL HEAVY or PASS) unless business
model and market position are both exceptional (scores ≥8.5). A strong product in a
structurally broken deal is still a CONDITIONAL HEAVY at best.

DEAL COMMITTEE NARRATIVE:
  Populate the `deal_committee_recommendation` field with 2-3 sentences in institutional
  ECM language summarizing the recommendation rationale for a deal committee audience.
  Lead with the recommendation (UNDERWRITE / CONDITIONAL_LIGHT / CONDITIONAL_HEAVY / PASS), state the primary
  driver (e.g., valuation, financial health, governance), and note the single most
  important risk or condition. This field is required — do not leave it empty.



\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
STRATEGIC ASSESSMENT FIELDS (required when conditions triggered)
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

These three fields are REQUIRED when the respective condition is detected.
Each must end with the exact one-sentence verdict so the analyst sees the
strategic conclusion immediately.

PROCEEDS_QUALITY_ASSESSMENT (required when RF-19 triggers):
  Evaluate: (1) what specific debt is retired and at what interest rate/maturity;
  (2) whether deleveraging materially improves risk profile and cost of capital;
  (3) whether remaining debt is sustainable post-IPO; (4) whether this is a PE exit /
  LBO unwind or strategic balance sheet repair; (5) whether cash flow covers remaining
  obligations; (6) long-term merit: does this strengthen the company, or transfer risk
  from private investors to the public without operational improvement?
  End with exactly one of:
    'Deleveraging is strategically sound and supports long-term value creation.'
  OR
    'Deleveraging primarily transfers risk to public investors without operational improvement.'

VALUATION_CEILING_ASSESSMENT (required when EV/EBITDA > 20x on a GAAP-loss company):
  Evaluate: (1) revenue growth rate and trend; (2) sector norms for premium multiples
  on a credible path-to-profitability thesis (AI, biotech, high-growth SaaS); (3)
  competitive moat and pricing power; (4) realistic timeline to breakeven; (5)
  precedent IPO comps in the same vertical.
  End with exactly one of:
    'Premium is supportable given [specific factor].'
  OR
    'Premium is not supportable at current growth and margin trajectory.'

LEVERAGE_ASSESSMENT (required when Debt/EBITDA > 4x on profitable, OR Debt/Adj.EBITDA
  > 6x with interest >20% of revenue on GAAP-loss):
  Evaluate: (1) sector-normal leverage ratio; (2) debt maturity and refinancing risk;
  (3) EBITDA/interest coverage trend; (4) whether IPO proceeds delever the balance sheet;
  (5) whether leverage is operational (growth capex, acquisition) or distressed.
  End with exactly one of:
    'Leverage is within sector norms and sustainable given the business model.'
  OR
    'Leverage exceeds sector norms and represents material refinancing/solvency risk.'
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
OUTPUT FORMAT -- RETURN AS VALID JSON ONLY
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

Return ONLY a valid JSON object. No prose before or after. No markdown fencing.
Use this exact schema:

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
    "proceeds_narrative": ""
  },

  "management": {
    "ceo_name": "",
    "ceo_tenure_months": null,
    "cfo_name": "",
    "cfo_tenure_months": null,
    "board_independent_pct": null,
    "founder_track_record_assessment": "",
    "founder_track_record_reasoning": "",
    "management_flags": []
  },

  "valuation": {
    "implied_ev_usd_millions": null,
    "ev_revenue_multiple": null,
    "ev_ebitda_multiple": null,
    "sector_median_ev_revenue": null,
    "premium_to_sector_median_pct": null,
    "public_comps": [
      {
        "name": "",
        "ticker": "",
        "ev_revenue": null,
        "ev_ebitda": null,
        "revenue_growth_pct": null
      }
    ],
    "valuation_flag": false,
    "primary_metric": "EV/EBITDA",
    "secondary_metric": "EV/Revenue",
    "methodology_rationale": "",
    "sector_classification": "standard_profitable",
    "sector_specific_metrics": {},
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
    "lockup_shares_count": null,
    "lockup_pct_of_outstanding": null,
    "lockup_structure_type": "",
    "lockup_release_schedule": [],
    "early_release_triggers": [],
    "parties_locked_up": [],
    "lockup_carveouts": [],
    "lockup_investor_assessment": "",
    "primary_shares_millions": null,
    "secondary_shares_millions": null,
    "secondary_shares_pct_offering": null,
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
      "first_day_pop_pct": null,
      "current_vs_offer_pct": null,
      "comp_type": "",
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

  "red_flags": [],
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

  "proceeds_quality_assessment": "",
  "valuation_ceiling_assessment": "",
  "leverage_assessment": "",

  "accounting_practices": {
    "items": [
      {
        "category": "Revenue Recognition",
        "key": "revenue_recognition",
        "description": "",
        "assessment": "",
        "earnings_impact": "",
        "risk_rating": ""
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

  "source_verification": {
    "tier_1_sources": [],
    "tier_2_sources": [],
    "tier_3_sources": []
  },

  "is_amendment": false,
  "prior_memo_date": null,
  "amendment_changes_summary": null
}
"""

# ─────────────────────────────────────────────
# EDGAR FETCHER
# ─────────────────────────────────────────────

def get_date_window() -> tuple[str, str]:
    """Return (start_date, today) as YYYY-MM-DD strings covering the past LOOKBACK_DAYS."""
    now = datetime.now(PACIFIC)
    start = (now - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    today = now.strftime("%Y-%m-%d")
    return start, today


def _load_saved_accessions() -> set:
    """Return the set of accession numbers already saved across all memo files."""
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


def fetch_new_s1_filings() -> list[dict]:
    """
    Fetch S-1 and S-1/A filings from the past LOOKBACK_DAYS days via EDGAR browse page.

    Restrictions applied (in order):
      1. Form type: S-1 and S-1/A only — excludes S-1MEF and other variants
      2. Date window: filing_date must fall within the last LOOKBACK_DAYS calendar days
      3. Dedup: accession numbers already saved in the memos directory are skipped
      4. Hard cap: returns at most MAX_FILINGS_PER_DAY results
    """
    start_date, today = get_date_window()
    log.info(f"Fetching EDGAR browse page — {LOOKBACK_DAYS}-day window ({start_date} → {today})")

    r = _edgar_get(EDGAR_BROWSE)
    if r is None:
        log.error("Failed to fetch EDGAR browse page")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        log.error("No tables found on EDGAR browse page")
        return []

    # The filings table is the largest by row count
    filing_table = max(tables, key=lambda t: len(t.find_all("tr")))
    rows = filing_table.find_all("tr")

    saved_accessions = _load_saved_accessions()

    filings      = []
    company_name = ""
    company_cik  = ""

    for row in rows:
        links = row.find_all("a", href=True)

        # Company header row — identified by the getcompany CIK link
        cik_link = next((a for a in links if "action=getcompany&CIK=" in a["href"]), None)
        if cik_link:
            raw_name     = cik_link.get_text(strip=True)
            company_name = re.sub(r"\s*\(\d+\)\s*\(Filer\)", "", raw_name).strip()
            m = re.search(r"CIK=(\d+)", cik_link["href"])
            company_cik  = m.group(1).lstrip("0") if m else ""
            continue

        # Filing detail row — identified by the -index.htm link
        idx_link = next((a for a in links if "-index.htm" in a["href"]), None)
        if not idx_link:
            continue

        tds       = row.find_all("td")
        form_type = tds[0].get_text(strip=True) if tds else ""

        # Restriction 1: S-1 and S-1/A only
        if form_type not in ALLOWED_FORMS:
            log.debug(f"Skipping {form_type} ({company_name}) — not an allowed form type")
            continue

        # Restriction 1b: real operating companies only — exclude SPACs, ETFs, trusts
        name_lower = company_name.lower()
        if any(kw in name_lower for kw in EXCLUDE_NAME_KEYWORDS):
            log.info(f"Skipping {company_name} — identified as shell/SPAC/ETF")
            continue

        # Extract accession number from the 18-digit folder segment in the URL
        m_acc = re.search(r"/data/\d+/(\d{18})/", idx_link["href"])
        if not m_acc:
            continue
        raw          = m_acc.group(1)
        accession_no = f"{raw[:10]}-{raw[10:12]}-{raw[12:]}"

        # Extract filing date — take the most recent YYYY-MM-DD in the row text.
        # For S-1/A rows the original S-1 date often appears first; max() picks the
        # amendment's actual filing date so same-day amendments pass the date filter.
        row_text   = row.get_text(separator=" ")
        dates      = re.findall(r"(20\d{2}-\d{2}-\d{2})", row_text)
        filing_date = max(dates) if dates else today

        # Restriction 2: 7-day window
        if filing_date < start_date:
            log.debug(f"Skipping {company_name} ({filing_date}) — outside {LOOKBACK_DAYS}-day window")
            continue

        # Restriction 3: skip already-analyzed filings
        if accession_no in saved_accessions:
            log.info(f"Skipping {company_name} ({accession_no}) — already analyzed")
            continue

        filings.append({
            "company":      company_name,
            "cik":          company_cik,
            "filing_date":  filing_date,
            "form_type":    form_type,
            "accession_no": accession_no,
        })

        # Restriction 4: hard cap
        if len(filings) >= MAX_FILINGS_PER_DAY:
            log.info(f"Reached MAX_FILINGS_PER_DAY cap ({MAX_FILINGS_PER_DAY}) — stopping fetch")
            break

    log.info(f"Found {len(filings)} qualifying S-1 filing(s) in window")
    return filings


def _edgar_get(url: str, timeout: int = 30):
    """GET from EDGAR with the required User-Agent header."""
    try:
        r = requests.get(url, headers=EDGAR_HEADERS, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        log.warning(f"EDGAR GET failed ({url}): {e}")
        return None


def fetch_filing_text(accession_no: str, cik: str, company: str) -> str:
    """
    Fetch the primary S-1 document text from EDGAR Archives.

    Strategy (in order):
      1. Fetch the filing's -index.json to identify the primary document.
      2. Download that document and strip to plain text (~80k chars).
      3. Fallback: try the EDGAR filing viewer page.
      4. Last resort: return a placeholder so Claude can still produce a stub memo.
    """
    if not accession_no:
        log.warning(f"No accession number for {company} -- skipping text fetch")
        return _filing_text_unavailable(company, accession_no)

    clean = accession_no.replace("-", "")

    # Step 1: Fetch the filing index JSON
    # URL: /Archives/edgar/data/{CIK}/{accession_nodash}/{accession}-index.json
    index_url = f"{EDGAR_BASE}/Archives/edgar/data/{cik}/{clean}/{accession_no}-index.json"
    log.info(f"Fetching filing index: {index_url}")
    index_r = _edgar_get(index_url)
    time.sleep(0.5)  # EDGAR rate-limit courtesy pause

    primary_doc_url = None

    if index_r:
        try:
            index_data = index_r.json()
            documents = index_data.get("documents", [])
            primary_doc_url = _pick_primary_document(documents, cik, clean)
        except Exception as e:
            log.warning(f"Could not parse index JSON for {company}: {e}")

    # Step 2: Fetch the primary document
    if primary_doc_url:
        log.info(f"Fetching primary document: {primary_doc_url}")
        doc_r = _edgar_get(primary_doc_url, timeout=90)
        time.sleep(0.5)
        if doc_r:
            return _strip_html(doc_r.text)

    # Step 3: Fallback -- EDGAR viewer page
    viewer_url = (
        f"{EDGAR_BASE}/cgi-bin/browse-edgar"
        f"?action=getcompany&CIK={cik}&type=S-1&dateb=&owner=include&count=5"
    )
    log.warning(f"Primary doc fetch failed for {company}; trying viewer: {viewer_url}")
    viewer_r = _edgar_get(viewer_url, timeout=30)
    time.sleep(0.5)
    if viewer_r:
        text = BeautifulSoup(viewer_r.text, "html.parser").get_text(separator="\n", strip=True)
        if len(text) > 500:
            return text[:80000]

    # Step 4: Give up gracefully
    log.error(f"All fetch attempts failed for {company} ({accession_no})")
    return _filing_text_unavailable(company, accession_no)


def _pick_primary_document(documents: list, cik: str, clean: str):
    """
    Given the documents list from EDGAR's -index.json, return the URL of the
    primary S-1 / prospectus document.

    Preference order:
      1. document whose type is exactly "S-1" or "S-1/A"
      2. document whose description contains "prospectus" (case-insensitive)
      3. the largest .htm / .html document in the filing (skipping index files)
    """
    base = f"{EDGAR_BASE}/Archives/edgar/data/{cik}/{clean}/"

    # Candidates by type match
    type_matches = [
        d for d in documents
        if d.get("type", "").upper() in ("S-1", "S-1/A")
        and d.get("filename", "").lower().endswith((".htm", ".html"))
    ]
    if type_matches:
        return base + type_matches[0]["filename"]

    # Candidates by description
    desc_matches = [
        d for d in documents
        if "prospectus" in d.get("description", "").lower()
        and d.get("filename", "").lower().endswith((".htm", ".html"))
    ]
    if desc_matches:
        return base + desc_matches[0]["filename"]

    # Largest .htm file (skip index files)
    htm_docs = [
        d for d in documents
        if d.get("filename", "").lower().endswith((".htm", ".html"))
        and "index" not in d.get("filename", "").lower()
    ]
    if htm_docs:
        htm_docs.sort(key=lambda d: int(d.get("size", 0) or 0), reverse=True)
        return base + htm_docs[0]["filename"]

    return None


def fetch_sic_for_cik(cik: str) -> tuple[str, str]:
    """
    Fetch the SIC code and description for a company from EDGAR's Submissions API.
    Returns (sic_code, sic_description) or ("", "") on failure.
    CIK is zero-padded to 10 digits as required by the API.
    """
    if not cik:
        return ("", "")
    try:
        padded = cik.zfill(10)
        url = f"https://data.sec.gov/submissions/CIK{padded}.json"
        r = requests.get(url, headers=EDGAR_HEADERS, timeout=15)
        if r.status_code != 200:
            log.warning(f"EDGAR Submissions API returned {r.status_code} for CIK {cik}")
            return ("", "")
        data = r.json()
        sic  = str(data.get("sic", "") or "")
        desc = str(data.get("sicDescription", "") or "")
        return (sic, desc)
    except Exception as e:
        log.warning(f"fetch_sic_for_cik failed for CIK {cik}: {e}")
        return ("", "")


def _strip_html(html: str) -> str:
    """Strip HTML tags and return plain text, capped at 80k chars."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n", strip=True)
    return text[:80000]


def _filing_text_unavailable(company: str, accession_no: str) -> str:
    return (
        f"[Filing text unavailable for {company} -- accession {accession_no}. "
        f"Analyze based on any available EDGAR data and produce a best-effort memo. "
        f"Mark data points as null where unknown.]"
    )


# ─────────────────────────────────────────────
# PRIOR MEMO LOOKUP  (for S-1/A diffing)
# ─────────────────────────────────────────────

def _company_slug(name: str) -> str:
    """Normalise a company name to its file slug."""
    return "".join(c if c.isalnum() else "_" for c in name.lower())[:40]


def find_prior_memo(company: str) -> tuple:
    """
    Search all dated memo directories for the most recent prior memo for this company.
    Returns (memo_dict, date_string) or (None, None).
    """
    slug = _company_slug(company)
    candidate_dirs = sorted(DATA_DIR.glob("????-??-??"), reverse=True)
    for date_dir in candidate_dirs:
        memo_path = date_dir / f"{slug}.json"
        if memo_path.exists():
            try:
                with open(memo_path) as f:
                    return json.load(f), date_dir.name
            except Exception as e:
                log.warning(f"Could not load prior memo {memo_path}: {e}")
    return None, None


# ─────────────────────────────────────────────
# CLAUDE ANALYSIS
# ─────────────────────────────────────────────

def _call_claude(client: anthropic.Anthropic, user_message: str, company: str) -> str:
    """
    Call Claude Opus with retry logic (up to MAX_RETRIES attempts,
    exponential backoff). Returns the raw text response.
    Raises the last exception if all retries are exhausted.
    """
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=OPUS_MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            return response.content[0].text.strip()
        except Exception as e:
            last_exc = e
            wait = RETRY_BASE_WAIT * (2 ** (attempt - 1))
            log.warning(
                f"Claude API attempt {attempt}/{MAX_RETRIES} failed for {company}: {e}. "
                f"Retrying in {wait}s..."
            )
            if attempt < MAX_RETRIES:
                time.sleep(wait)
    raise last_exc


def _parse_claude_json(raw: str) -> dict:
    """Strip accidental markdown fences and parse JSON."""
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


# ─────────────────────────────────────────────
# PRE-ANALYSIS ELIGIBILITY GATE
# ─────────────────────────────────────────────

# SIC codes that identify non-operating entities ineligible for ECM screening
_INELIGIBLE_SIC_CODES: dict[str, str] = {
    "6770": "Blank Check Company",
    "6726": "Investment Office (SPAC / Closed-End Fund / BDC)",
    "6798": "Real Estate Investment Trust (REIT)",
}

# Filing form types that identify non-operating registrations
_INELIGIBLE_FORM_TYPES: dict[str, str] = {
    "S-11": "REIT",
    "N-2":  "Closed-End Fund / BDC",
}

# Company name substrings (lower-cased) that identify non-operating entities
_INELIGIBLE_NAME_PATTERNS: list[tuple[str, str]] = [
    ("acquisition corp",            "Blank Check Company"),
    ("acquisition corporation",     "Blank Check Company"),
    ("blank check",                 "Blank Check Company"),
    ("spac",                        "SPAC"),
    ("special purpose acquisition", "SPAC"),
    ("royalty trust",               "Royalty Trust"),
    ("income trust",                "Income Trust"),
    ("investment trust",            "Investment Trust"),
]


def validate_company_type(
    company_name: str,
    sic_code: str,
    filing_type: str,
) -> tuple[bool, str]:
    """
    Pre-analysis eligibility gate. Returns (is_eligible, abort_message).

    Checks (in order):
      1. Filing form type against _INELIGIBLE_FORM_TYPES
      2. SIC code against _INELIGIBLE_SIC_CODES
      3. Company name against _INELIGIBLE_NAME_PATTERNS

    If any check fails, is_eligible=False and abort_message contains the
    formatted reason. Must be called BEFORE fetch_filing_text() — this is a
    hard gate with no bypass.
    """
    name_lower = (company_name or "").lower()

    # 1. Form type check (available before any network call)
    if filing_type in _INELIGIBLE_FORM_TYPES:
        entity_label = _INELIGIBLE_FORM_TYPES[filing_type]
        msg = (
            f"ANALYSIS ABORTED — {company_name} is a {entity_label} "
            f"based on SIC code {sic_code or 'unknown'} and filing type {filing_type}. "
            "This screener is designed for operating company IPOs only. "
            "Non-operating entities are not eligible for ECM due diligence screening."
        )
        return False, msg

    # 2. SIC code check (populated after fetch_sic_for_cik)
    if sic_code and sic_code in _INELIGIBLE_SIC_CODES:
        entity_label = _INELIGIBLE_SIC_CODES[sic_code]
        msg = (
            f"ANALYSIS ABORTED — {company_name} is a {entity_label} "
            f"based on SIC code {sic_code} and filing type {filing_type}. "
            "This screener is designed for operating company IPOs only. "
            "Non-operating entities are not eligible for ECM due diligence screening."
        )
        return False, msg

    # 3. Company name pattern check
    for pattern, entity_label in _INELIGIBLE_NAME_PATTERNS:
        if pattern in name_lower:
            msg = (
                f"ANALYSIS ABORTED — {company_name} is a {entity_label} "
                f"based on SIC code {sic_code or 'unknown'} and filing type {filing_type}. "
                "This screener is designed for operating company IPOs only. "
                "Non-operating entities are not eligible for ECM due diligence screening."
            )
            return False, msg

    return True, ""


# ─────────────────────────────────────────────
# CONTENT TRIAGE (keyword matching — no API)
# ─────────────────────────────────────────────

# (keyword, entity_type) — checked in order against the first 15,000 chars of filing text
_TRIAGE_RULES = [
    # Non-operating shells — cover page phrases (per eligibility gate spec)
    ("blank check company",                        "SPAC"),
    ("no specific business plan",                  "SPAC"),
    ("business combination",                       "SPAC"),
    ("trust account",                              "SPAC"),
    ("exchange-traded fund",                       "ETF"),
    ("exchange traded fund",                       "ETF"),
    # Secondary / follow-on offerings (already-public company, selling stockholder shares)
    ("selling stockholders will receive all",      "SECONDARY"),
    ("we will not receive any proceeds",           "SECONDARY"),
    ("all of the shares offered by this prospectus are being sold by the selling", "SECONDARY"),
    ("all proceeds from the sale of shares will be received by the selling",       "SECONDARY"),
    ("our shares of common stock are listed on",   "SECONDARY"),
    ("shares of our common stock are listed on the nasdaq", "SECONDARY"),
    ("shares of our common stock are listed on the new york stock exchange",       "SECONDARY"),
    ("shares of our class a common stock are listed on", "SECONDARY"),
]


def triage_filing(filing_text: str, company: str) -> dict:
    """
    Classify a filing as OPERATING_COMPANY or a non-operating entity using keyword
    matching on the first 8,000 characters of the document. No API calls.

    Returns: {"entity_type": str, "skip": bool, "reason": str}
    """
    excerpt = filing_text[:15000].lower()
    for keyword, entity_type in _TRIAGE_RULES:
        if keyword in excerpt:
            reason = f'Filing contains "{keyword}" — classified as {entity_type}'
            log.info(f"SKIP (triage) {company}: {entity_type} — {reason}")
            return {"entity_type": entity_type, "skip": True, "reason": reason}
    log.info(f"PASS (triage) {company}: OPERATING_COMPANY")
    return {"entity_type": "OPERATING_COMPANY", "skip": False, "reason": "no non-operating keywords found"}


def _skip_stub(
    company: str,
    filing_date: str,
    form_type: str,
    entity_type: str,
    reason: str,
) -> dict:
    """Build a lightweight PASS stub for non-operating entities skipped at triage."""
    return {
        "company_name":   company,
        "filing_date":    filing_date,
        "form_type":      form_type,
        "recommendation": "PASS",
        "going_concern":  False,
        "red_flags":      [],
        "red_flag_count": 0,
        "scores":         {"weighted_total": None},
        "pass_reasons":   [
            f"TRIAGE SKIP — Entity classified as {entity_type} by pre-screen. "
            f"{reason}. Not an operating company; cannot underwrite."
        ],
        "executive_summary": (
            f"{company} was classified as {entity_type} during Haiku triage and excluded "
            f"from full analysis. {reason}."
        ),
        "is_amendment":               form_type == "S-1/A",
        "prior_memo_date":            None,
        "amendment_changes_summary":  None,
        "_triage_entity_type":        entity_type,
        "run_timestamp":              datetime.now(PACIFIC).isoformat(),
    }


def fetch_external_comps(client: anthropic.Anthropic, company_name: str,
                          sector: str, sic_code: str) -> list:
    """
    Pre-analysis comps step — mirrors the /comps slash command workflow.

    1. Uses COMPS_MODEL (Sonnet) to identify 4–6 comparable public companies
       based on company name, sector, and SIC code.
    2. Enriches each with live market data from yfinance:
       ev_revenue, ev_ebitda, revenue_growth_pct.
    3. Returns a list of comp dicts for injection into the Opus analysis prompt
       as [EXTERNAL COMPS DATA — source: /comps].

    Falls back to empty list on any error so the main analysis is unaffected.
    """
    sic_line = f"SIC code: {sic_code}" if sic_code else ""
    prompt = (
        f"You are a capital markets analyst. Identify 4–6 publicly traded comparable companies for:\n"
        f"Company: {company_name}\n"
        f"Sector / Industry: {sector or 'unknown'} {sic_line}\n\n"
        "Select peers by: similar business model, comparable revenue scale, same SIC or adjacent sector.\n"
        "Prioritize companies with positive EBITDA where feasible for EV/EBITDA comps.\n\n"
        "Return ONLY a valid JSON array with no markdown fences. Each element:\n"
        '{"name":"Full Company Name","ticker":"TICKER","rationale":"1-sentence reason"}\n'
    )
    try:
        resp = client.messages.create(
            model=COMPS_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
        comps_raw = json.loads(raw)
        if not isinstance(comps_raw, list):
            return []
    except Exception as e:
        log.warning(f"fetch_external_comps: identification failed for {company_name}: {e}")
        return []

    try:
        import yfinance as yf
    except ImportError:
        log.info("yfinance not installed — external comps returned without live metrics")
        return [
            {"name": c.get("name", ""), "ticker": c.get("ticker", ""),
             "ev_revenue": None, "ev_ebitda": None, "revenue_growth_pct": None,
             "rationale": c.get("rationale", ""), "source": "comps_skill"}
            for c in comps_raw[:6]
        ]

    enriched = []
    for c in comps_raw[:6]:
        ticker = (c.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        comp_obj = {
            "name":               c.get("name", ticker),
            "ticker":             ticker,
            "ev_revenue":         None,
            "ev_ebitda":          None,
            "revenue_growth_pct": None,
            "rationale":          c.get("rationale", ""),
            "source":             "comps_skill",
        }
        try:
            info   = yf.Ticker(ticker).info
            ev     = info.get("enterpriseValue")
            rev    = info.get("totalRevenue")
            ebitda = info.get("ebitda")
            growth = info.get("revenueGrowth")   # decimal e.g. 0.15 → 15%
            if ev and rev and rev > 0:
                comp_obj["ev_revenue"] = round(ev / rev, 1)
            if ev and ebitda and ebitda > 0:
                comp_obj["ev_ebitda"] = round(ev / ebitda, 1)
            if growth is not None:
                comp_obj["revenue_growth_pct"] = round(growth * 100, 1)
            time.sleep(0.3)
        except Exception as e:
            log.warning(f"fetch_external_comps: yfinance failed for {ticker}: {e}")
        enriched.append(comp_obj)

    log.info(f"External comps fetched: {[c['ticker'] for c in enriched]}")
    return enriched


def fetch_unit_economics(client: anthropic.Anthropic, company_name: str,
                          sector: str, filing_text: str) -> dict:
    """
    Pre-analysis unit economics step — mirrors the /unit-economics slash command workflow.

    Sends the first 20k characters of the S-1 (covers MD&A and financial highlights) to
    COMPS_MODEL (Sonnet) with a targeted extraction prompt. Returns a dict of five metrics:
      nrr_pct              — Net Revenue Retention %
      cac_ltv_ratio        — LTV/CAC ratio (higher = better; e.g. 4.2 means LTV is 4.2× CAC)
      rule_of_40           — Revenue growth % + Gross margin %
      sbc_pct_revenue      — Stock-Based Compensation as % of Revenue
      deferred_revenue_trend — "growing" | "stable" | "declining" | "not_applicable"

    Falls back to empty dict on any error. Null values indicate the metric was not
    disclosed or is not applicable to this business model.
    """
    filing_snippet = filing_text[:20_000]
    prompt = (
        f"You are an expert IPO analyst performing unit economics analysis per the "
        f"/unit-economics workflow.\n\n"
        f"Company: {company_name}\n"
        f"Sector: {sector or 'unknown'}\n\n"
        "Extract the following unit economics metrics from the SEC S-1 filing text below. "
        "Return null for any metric that is not disclosed, cannot be reliably derived from "
        "the text, or is not applicable to this business model (e.g. NRR for a "
        "pure-transactional company with no subscription revenue).\n\n"
        "Return ONLY a valid JSON object — no markdown, no explanation:\n"
        "{\n"
        '  "nrr_pct": number|null,\n'
        '  "cac_ltv_ratio": number|null,\n'
        '  "rule_of_40": number|null,\n'
        '  "sbc_pct_revenue": number|null,\n'
        '  "deferred_revenue_trend": "growing"|"stable"|"declining"|"not_applicable"|null\n'
        "}\n\n"
        "Definitions:\n"
        "  nrr_pct             — Net Revenue Retention %, also called Dollar-Based Net "
        "Expansion Rate. Express as a whole number (e.g. 118, not 1.18).\n"
        "  cac_ltv_ratio       — LTV divided by CAC (higher is better). If only CAC/LTV is "
        "disclosed, invert it. If LTV/CAC = 4.2, return 4.2.\n"
        "  rule_of_40          — Revenue growth % (YoY) PLUS Gross margin %. Compute if "
        "both figures are available in the text; otherwise null.\n"
        "  sbc_pct_revenue     — Stock-Based Compensation as a percentage of TTM revenue. "
        "Extract from income statement footnotes or operating expense breakdown.\n"
        "  deferred_revenue_trend — Direction of deferred revenue balance change over the "
        "most recent reported period. Use 'not_applicable' for non-subscription models.\n\n"
        "Do NOT fabricate numbers. Only return values you can directly extract or compute "
        "from the text below.\n\n"
        f"FILING TEXT (first 20,000 characters):\n{filing_snippet}\n"
    )
    try:
        resp = client.messages.create(
            model=COMPS_MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
        result = json.loads(raw)
        if not isinstance(result, dict):
            return {}
        # Sanitize — keep only the five expected keys with correct types
        clean = {}
        for k in ("nrr_pct", "cac_ltv_ratio", "rule_of_40", "sbc_pct_revenue"):
            v = result.get(k)
            clean[k] = float(round(v, 2)) if isinstance(v, (int, float)) else None
        drt = result.get("deferred_revenue_trend")
        valid_drt = {"growing", "stable", "declining", "not_applicable"}
        clean["deferred_revenue_trend"] = drt if isinstance(drt, str) and drt in valid_drt else None
        log.info(f"Unit economics fetched for {company_name}: {clean}")
        return clean
    except Exception as e:
        log.warning(f"fetch_unit_economics failed for {company_name}: {e}")
        return {}


def fetch_diligence_checklist(client: anthropic.Anthropic, company_name: str,
                               sector: str, filing_text: str) -> list:
    """
    Pre-analysis diligence step — mirrors the /dd-checklist slash command workflow.

    Sends the first 25k characters of the S-1 to COMPS_MODEL (Sonnet) with a
    structured checklist prompt. Returns a list of diligence findings, each mapped
    to an RF code where applicable, for injection as [EXTERNAL DILIGENCE DATA] context
    and for Python-side cross-referencing against Opus's red_flags[].

    Each item: {category, finding, severity, rf_code_match, diligence_triggered}
    Falls back to empty list on any error.
    """
    filing_snippet = filing_text[:25_000]
    prompt = (
        f"You are a senior IPO due diligence analyst performing a /dd-checklist review.\n\n"
        f"Company: {company_name}\n"
        f"Sector: {sector or 'unknown'}\n\n"
        "Review the SEC S-1 filing text below. Identify ALL material red flags, risks, and "
        "diligence concerns an underwriting desk should be aware of. For each finding:\n"
        "  - Assign a category (e.g. Revenue Quality, Capital Structure, Governance, etc.)\n"
        "  - Write a concise factual finding (1-2 sentences, cite the specific fact)\n"
        "  - Rate severity: HIGH, MEDIUM, or LOW\n"
        "  - Map to the closest RF code from this framework where applicable:\n"
        "    RF-01 Going Concern | RF-02 Customer Concentration | RF-03 Revenue Quality\n"
        "    RF-04 Insider Liquidity | RF-05 Runway Risk | RF-06 Governance Risk\n"
        "    RF-07 Valuation Disconnect | RF-08 Management Red Flags | RF-09 Related Party\n"
        "    RF-10 Audit Issues | RF-11 Margin Risk | RF-12 Regulatory Overhang\n"
        "    RF-13 Market Timing | RF-14 Capital Structure Risk | RF-15 Product Concentration\n"
        "    RF-16 Geographic Concentration | RF-17 Technology Obsolescence\n"
        "    RF-18 Working Capital Stress | RF-19 Proceeds Quality | RF-20 Syndicate Spread\n"
        "    RF-21 PE/Sponsor Overhang | RF-22 Small Firm Suitability\n"
        "    RF-23 Insider Liquidity Overhang | RF-24 Auditor Quality | RF-25 Accounting Quality\n"
        "  - Set diligence_triggered: true for any finding that warrants underwriter attention\n\n"
        "Return ONLY a valid JSON array with no markdown. Each element:\n"
        "{\n"
        '  "category": "string",\n'
        '  "finding": "string",\n'
        '  "severity": "HIGH"|"MEDIUM"|"LOW",\n'
        '  "rf_code_match": "RF-XX"|null,\n'
        '  "diligence_triggered": true|false\n'
        "}\n\n"
        "Return an empty array [] if the filing text is insufficient to make findings. "
        "Do NOT fabricate — only report what the text supports.\n\n"
        f"FILING TEXT (first 25,000 characters):\n{filing_snippet}\n"
    )
    try:
        resp = client.messages.create(
            model=COMPS_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
        items = json.loads(raw)
        if not isinstance(items, list):
            return []
        # Sanitize — keep only triggered items with required fields
        clean = []
        for item in items:
            if not isinstance(item, dict):
                continue
            clean.append({
                "category":           str(item.get("category", "Diligence Finding")),
                "finding":            str(item.get("finding", "")),
                "severity":           str(item.get("severity", "MEDIUM")).upper(),
                "rf_code_match":      item.get("rf_code_match") if isinstance(item.get("rf_code_match"), str) else None,
                "diligence_triggered": bool(item.get("diligence_triggered", True)),
            })
        log.info(f"Diligence checklist fetched for {company_name}: {len(clean)} findings")
        return clean
    except Exception as e:
        log.warning(f"fetch_diligence_checklist failed for {company_name}: {e}")
        return []


# RF keyword map used by cross_reference_flags() for text-based fallback matching
_RF_KEYWORD_MAP = {
    "RF-01": ["going concern", "liquidity doubt", "ability to continue"],
    "RF-02": ["customer concentration", "top customer", "largest customer", "single customer"],
    "RF-03": ["revenue quality", "accounts receivable", "channel stuff", "deferred revenue declin"],
    "RF-04": ["insider", "secondary shares", "selling shareholder", "founder sell"],
    "RF-05": ["runway", "cash burn", "months of cash"],
    "RF-06": ["governance", "dual class", "voting control", "classified board"],
    "RF-07": ["valuation disconnect", "ev/revenue", "sector median", "overvalued"],
    "RF-08": ["ceo tenure", "cfo tenure", "management flag", "sec enforcement", "prior failure"],
    "RF-09": ["related party"],
    "RF-10": ["material weakness", "internal control", "auditor change", "restatement"],
    "RF-11": ["gross margin", "negative margin", "inverted unit economics"],
    "RF-12": ["regulatory", "sec investigation", "doj", "litigation overhang"],
    "RF-13": ["market timing", "failed ipo", "sector downturn"],
    "RF-14": ["capital structure", "covenant", "pik debt", "convertible dilut", "leverage"],
    "RF-15": ["product concentration", "single product", "one product"],
    "RF-16": ["geographic concentration", "single geography", "single country"],
    "RF-17": ["technology obsolescence", "ai disruption", "open source threat"],
    "RF-18": ["working capital", "current ratio", "negative working capital"],
    "RF-19": ["proceeds quality", "debt repayment", "sponsor distribution", "non-operational"],
    "RF-20": ["syndicate spread", "co-manager", "underwriter count"],
    "RF-21": ["sponsor overhang", "pe ownership", "lockup expiry"],
    "RF-22": ["small firm", "offering size", "pre-revenue"],
    "RF-23": ["insider liquidity overhang", "secondary offering"],
    "RF-24": ["auditor quality", "non-big 4", "regional auditor", "unknown auditor"],
    "RF-25": ["accounting quality", "aggressive accounting", "non-gaap adjust"],
}


def cross_reference_flags(memo: dict, diligence_items: list) -> dict:
    """
    Cross-reference Opus red_flags[] against /diligence checklist items (Python-side).

    Rules (no-duplication guarantee):
      1. Exact RF code match: normalize codes ("RF-01A" → "RF-01") and match
         each diligence item's rf_code_match against Opus flags.
      2. Keyword fallback: if rf_code_match is null, infer RF code from finding
         text via _RF_KEYWORD_MAP and attempt to match Opus flags that way.
      3. Matched Opus flag → set dual_source_confirmed = True on that flag.
         The diligence item is consumed; no new flag is added.
      4. Unmatched triggered diligence item → append new flag object with
         source = "diligence_only". Never added twice (set tracks consumed items).
      5. red_flag_count updated to include diligence_only entries.
    """
    if not diligence_items:
        return memo

    flags = list(memo.get("red_flags") or [])

    def _norm(code: str) -> str:
        """RF-01A → RF-01, RF-07B → RF-07, RF-07 → RF-07"""
        if not code:
            return ""
        c = code.strip().upper()
        # Strip trailing single letter variant suffix (A, B but not a digit)
        c = re.sub(r'(RF-\d+)[A-Z]$', r'\1', c)
        return c

    def _infer_rf_from_text(item: dict) -> str:
        text = (item.get("finding", "") + " " + item.get("category", "")).lower()
        for code, keywords in _RF_KEYWORD_MAP.items():
            if any(kw in text for kw in keywords):
                return code
        return ""

    # Build lookup: normalized RF code → list of flag indices in Opus output
    opus_by_code: dict[str, list[int]] = {}
    for i, f in enumerate(flags):
        if not isinstance(f, dict):
            continue
        raw_code = f.get("flag_id") or f.get("code") or ""
        norm = _norm(raw_code)
        if norm:
            opus_by_code.setdefault(norm, []).append(i)

    consumed: set[int] = set()   # diligence item indices that matched an Opus flag

    # Pass 1 — RF-code-match first (exact, then keyword fallback)
    for i, item in enumerate(diligence_items):
        if not item.get("diligence_triggered", True):
            continue
        rf = _norm(item.get("rf_code_match") or "")
        if not rf:
            rf = _infer_rf_from_text(item)
        matched_indices = opus_by_code.get(rf, [])
        if matched_indices:
            for idx in matched_indices:
                flags[idx]["dual_source_confirmed"] = True
            consumed.add(i)
            log.debug(f"Diligence item {i} ({rf}) confirmed Opus flag(s) at index {matched_indices}")

    # Pass 2 — unmatched triggered items → diligence_only flags
    for i, item in enumerate(diligence_items):
        if i in consumed:
            continue
        if not item.get("diligence_triggered", True):
            continue
        flags.append({
            "flag_id":              "DILIGENCE",
            "code":                 "DILIGENCE",
            "label":                item.get("category", "Diligence Finding"),
            "description":          item.get("finding", ""),
            "narrative":            item.get("finding", ""),
            "severity":             item.get("severity", "MEDIUM"),
            "triggered":            True,
            "score_deduction":      None,
            "affected_dimension":   "Review Required",
            "source":               "diligence_only",
            "dual_source_confirmed": False,
        })
        log.debug(f"Diligence item {i} added as diligence_only: {item.get('category')}")

    memo["red_flags"]    = flags
    memo["red_flag_count"] = sum(
        1 for f in flags
        if isinstance(f, dict) and f.get("triggered") is not False
    )
    memo["diligence_cross_referenced"] = True
    return memo


def analyze_filing(client: anthropic.Anthropic, filing: dict) -> dict:
    """
    Analyze a single S-1 filing with Claude Opus.

    For S-1/A amendments, loads the prior memo and asks Claude to compare
    and summarize what changed. On Claude API failure (after all retries),
    saves a stub memo with recommendation='ERROR' and the raw response (if any)
    for manual review.
    """
    company     = filing.get("company", "Unknown")
    accession   = filing.get("accession_no", "")
    cik         = filing.get("cik", "")
    filing_date = filing.get("filing_date", "")
    form_type   = filing.get("form_type", "S-1")

    log.info(f"Analyzing: {company} ({form_type})")

    # ── STEP 1: Form type + name eligibility check (no network required) ──
    is_eligible, abort_msg = validate_company_type(company, "", form_type)
    if not is_eligible:
        print(f"\n{'='*72}\n{abort_msg}\n{'='*72}\n")
        log.warning(abort_msg)
        return _skip_stub(company, filing_date, form_type, "NON_OPERATING_ENTITY", abort_msg)

    # ── STEP 2: Fetch SIC code from EDGAR Submissions API (before S-1 fetch) ──
    sic_code, sic_description = fetch_sic_for_cik(cik)
    if sic_code:
        log.info(f"SIC {sic_code} — {sic_description}")
    time.sleep(0.5)  # EDGAR rate-limit courtesy pause

    # ── STEP 3: Full eligibility gate with SIC code — hard stop before any S-1 fetch ──
    is_eligible, abort_msg = validate_company_type(company, sic_code, form_type)
    if not is_eligible:
        print(f"\n{'='*72}\n{abort_msg}\n{'='*72}\n")
        log.warning(abort_msg)
        return _skip_stub(company, filing_date, form_type, "NON_OPERATING_ENTITY", abort_msg)

    # ── STEP 4: Eligible — now safe to fetch S-1 text ──
    filing_text = fetch_filing_text(accession, cik, company)
    time.sleep(1)  # additional courtesy pause between fetch and API call

    # ── STEP 5: Content triage (keyword match on filing text — catches cover page phrases) ──
    triage = triage_filing(filing_text, company)
    if triage.get("skip"):
        log.info(
            f"SKIP (triage) {company} — {triage['entity_type']}: {triage['reason']}"
        )
        return _skip_stub(
            company, filing_date, form_type,
            triage["entity_type"], triage["reason"]
        )

    # Amendment diffing
    amendment_context = ""
    if form_type == "S-1/A":
        prior_memo, prior_date = find_prior_memo(company)
        if prior_memo:
            prior_summary = {
                "filing_date":       prior_memo.get("filing_date"),
                "recommendation":    prior_memo.get("recommendation"),
                "score":             (prior_memo.get("scores") or {}).get("weighted_total"),
                "red_flag_count":    prior_memo.get("red_flag_count"),
                "executive_summary": prior_memo.get("executive_summary", "")[:500],
                "conditions":        prior_memo.get("conditions", []),
                "pass_reasons":      prior_memo.get("pass_reasons", []),
                "red_flags":         prior_memo.get("red_flags", []),
                "financials":        prior_memo.get("financials", {}),
            }
            amendment_context = f"""
AMENDMENT CONTEXT -- PRIOR S-1 MEMO (dated {prior_date})
This is a S-1/A amendment. The company previously filed an S-1 on {prior_date}.
Prior screening result: {prior_summary['recommendation']} (score: {prior_summary['score']})

Prior memo summary (abbreviated):
{json.dumps(prior_summary, indent=2)}

Your additional tasks for this amendment:
1. Identify what materially changed between the original S-1 and this amendment.
2. Assess whether the changes improve or worsen the deal profile.
3. Update your recommendation accordingly.
4. Set "is_amendment" to true, "prior_memo_date" to "{prior_date}".
5. Populate "amendment_changes_summary" with a concise narrative of the key changes
   (2-4 sentences). Focus on: pricing updates, financial restatements, new risk factors,
   changes to use of proceeds, management changes, or underwriter changes.
"""
        else:
            amendment_context = (
                "\nThis is a S-1/A amendment, but no prior S-1 memo was found in the "
                "memos directory for this company. Analyze as a fresh filing. "
                "Set is_amendment=true and prior_memo_date=null."
            )

    # ── External comps pre-fetch (/comps — runs before Opus) ──────────────────
    external_comps = []
    try:
        external_comps = fetch_external_comps(
            client, company, sic_description or "", sic_code or ""
        )
    except Exception as e:
        log.warning(f"External comps fetch failed for {company}: {e}")

    # ── Unit economics pre-fetch (/unit-economics — runs before Opus) ─────────
    unit_econ = {}
    try:
        unit_econ = fetch_unit_economics(
            client, company, sic_description or "", filing_text
        )
    except Exception as e:
        log.warning(f"External unit economics fetch failed for {company}: {e}")

    ue_context = ""
    if unit_econ:
        def _ue_fmt(v):
            return str(round(v, 2)) if isinstance(v, (int, float)) else "null"
        ue_lines = [
            f"  nrr_pct:               {_ue_fmt(unit_econ.get('nrr_pct'))}",
            f"  cac_ltv_ratio:         {_ue_fmt(unit_econ.get('cac_ltv_ratio'))}",
            f"  rule_of_40:            {_ue_fmt(unit_econ.get('rule_of_40'))}",
            f"  sbc_pct_revenue:       {_ue_fmt(unit_econ.get('sbc_pct_revenue'))}",
            f"  deferred_revenue_trend: {unit_econ.get('deferred_revenue_trend') or 'null'}",
        ]
        ue_context = (
            "\n[EXTERNAL UNIT ECONOMICS DATA — source: /unit-economics]\n"
            + "\n".join(ue_lines)
            + "\nCopy these values into financials{} per the instructions in your system prompt.\n"
        )

    # ── Diligence checklist pre-fetch (/diligence — runs before Opus) ────────
    diligence_items = []
    try:
        diligence_items = fetch_diligence_checklist(
            client, company, sic_description or "", filing_text
        )
    except Exception as e:
        log.warning(f"Diligence checklist fetch failed for {company}: {e}")

    diligence_context = ""
    if diligence_items:
        d_lines = []
        for item in diligence_items:
            rf_tag = f" | RF: {item['rf_code_match']}" if item.get("rf_code_match") else ""
            d_lines.append(
                f"  [{item['severity']}]{rf_tag} | {item['category']}\n"
                f"    {item['finding']}"
            )
        diligence_context = (
            "\n[EXTERNAL DILIGENCE DATA — source: /diligence]\n"
            + "\n".join(d_lines)
            + "\nCross-reference these findings against your own red flag analysis. "
            "Ensure any concern flagged here is covered in your red_flags[]. "
            "Do NOT set dual_source_confirmed — the pipeline handles that post-analysis.\n"
        )

    comps_context = ""
    if external_comps:
        lines = []
        for c in external_comps:
            ev_rev    = f"{c['ev_revenue']}x"         if c.get("ev_revenue")         is not None else "N/A"
            ev_ebitda = f"{c['ev_ebitda']}x"          if c.get("ev_ebitda")          is not None else "N/A"
            rev_grow  = f"{c['revenue_growth_pct']}%" if c.get("revenue_growth_pct") is not None else "N/A"
            lines.append(
                f"  {c['ticker']:<8} {c['name'][:40]:<40} "
                f"EV/Rev: {ev_rev:<8} EV/EBITDA: {ev_ebitda:<8} RevGrowth: {rev_grow}"
            )
        comps_context = (
            "\n[EXTERNAL COMPS DATA — source: /comps]\n"
            + "\n".join(lines)
            + "\nUse these pre-fetched comps to populate valuation.public_comps[] objects "
            "exactly as specified in the schema. Copy ev_revenue, ev_ebitda, and "
            "revenue_growth_pct values from this table; set null where listed as N/A.\n"
        )

    edgar_url = (
        f"https://www.sec.gov/cgi-bin/browse-edgar"
        f"?action=getcompany&CIK={cik}&type=S-1&dateb=&owner=include&count=10"
    )
    sic_line = f"SIC Code: {sic_code} — {sic_description}" if sic_code else "SIC Code: not available"
    user_message = f"""
Analyze the following SEC {form_type} filing for {company}.
Filing date: {filing_date}
Accession number: {accession}
CIK: {cik}
{sic_line}
{amendment_context}{ue_context}{diligence_context}{comps_context}
FILING TEXT (may be truncated to ~80,000 characters):
{filing_text}

Produce the complete IPO Screening Memo as a valid JSON object per the schema in your instructions.
If certain data points are not available in the text, use null. Do not fabricate numbers.
Set filing_url to: {edgar_url}
"""

    raw_response = None
    try:
        raw_response = _call_claude(client, user_message, company)
        memo = _parse_claude_json(raw_response)
        memo["company_name"]    = memo.get("company_name") or company
        memo["filing_date"]     = memo.get("filing_date")  or filing_date
        memo["form_type"]       = form_type
        memo["run_timestamp"]   = datetime.now(PACIFIC).isoformat()
        # Back-fill SIC from EDGAR — authoritative, don't let the model override
        if sic_code:
            memo["sic_code"]        = sic_code
            memo["sic_description"] = sic_description
        # Ensure amendment fields always present
        memo.setdefault("is_amendment", form_type == "S-1/A")
        memo.setdefault("prior_memo_date", None)
        memo.setdefault("amendment_changes_summary", None)
        # Back-fill unit economics into financials{} if pre-fetch succeeded
        # (Opus should have already used these values, but this ensures schema integrity)
        if unit_econ:
            fin = memo.setdefault("financials", {})
            _ue_map = {
                "nrr_pct":                    "nrr_pct",
                "cac_ltv_ratio":              "cac_ltv_ratio",
                "rule_of_40":                 "rule_of_40_score",
                "sbc_pct_revenue":            "stock_based_comp_pct_revenue",
                "deferred_revenue_trend":     "deferred_revenue_trend",
            }
            for ue_key, fin_key in _ue_map.items():
                fetched = unit_econ.get(ue_key)
                if fetched is not None and fin.get(fin_key) is None:
                    fin[fin_key] = fetched
            memo["unit_econ_enriched"] = True
        # Cross-reference Opus flags against /diligence checklist (Python-side)
        if diligence_items:
            memo = cross_reference_flags(memo, diligence_items)
        memo = enrich_valuation_with_live_comps(memo)
        memo = enrich_with_damodaran(memo)
        memo = enrich_valuation_metric_selection(memo)
        memo = apply_scoring_adjustments(memo)
        return memo

    except json.JSONDecodeError as e:
        log.error(f"JSON parse error for {company} after all retries: {e}")
        return _error_stub(company, filing_date, form_type, f"JSON parse error: {e}", raw_response)

    except Exception as e:
        log.error(f"Claude API failed for {company} after {MAX_RETRIES} retries: {e}")
        return _error_stub(company, filing_date, form_type, str(e), raw_response)


# ─────────────────────────────────────────────
# DAMODARAN INDUSTRY MULTIPLES
# ─────────────────────────────────────────────

# Module-level cache — fetched once per process run, not per filing
_damodaran_cache: dict | None = None

# Sector keyword → Damodaran industry name mapping
# Keys are lowercase fragments that may appear in a company's sector/subsector field.
# Order matters: more specific entries should come first.
_SECTOR_MAP = [
    ("software (internet)",        "Software (Internet)"),
    ("internet",                   "Software (Internet)"),
    ("saas",                       "Software (System & Application)"),
    ("software",                   "Software (System & Application)"),
    ("semiconductor equip",        "Semiconductor Equip"),
    ("semiconductor",              "Semiconductor"),
    ("computer",                   "Computer Services"),
    ("biotechnology",              "Drugs (Biotechnology)"),
    ("biotech",                    "Drugs (Biotechnology)"),
    ("pharmaceutical",             "Drugs (Pharmaceutical)"),
    ("pharma",                     "Drugs (Pharmaceutical)"),
    ("healthcare information",     "Heathcare Information and Technology"),
    ("health tech",                "Heathcare Information and Technology"),
    ("healthtech",                 "Heathcare Information and Technology"),
    ("medical device",             "Healthcare Products"),
    ("healthcare product",         "Healthcare Products"),
    ("hospital",                   "Hospitals/Healthcare Facilities"),
    ("healthcare support",         "Healthcare Support Services"),
    ("healthcare",                 "Healthcare Products"),
    ("telecom equip",              "Telecom. Equipment"),
    ("telecom wireless",           "Telecom (Wireless)"),
    ("wireless",                   "Telecom (Wireless)"),
    ("telecom",                    "Telecom. Services"),
    ("financial service",          "Financial Svcs. (Non-bank & Insurance)"),
    ("fintech",                    "Financial Svcs. (Non-bank & Insurance)"),
    ("brokerage",                  "Brokerage & Investment Banking"),
    ("investment banking",         "Brokerage & Investment Banking"),
    ("insurance",                  "Insurance (General)"),
    ("asset management",           "Investments & Asset Management"),
    ("real estate",                "Real Estate (General/Diversified)"),
    ("reit",                       "R.E.I.T."),
    ("retail",                     "Retail (General)"),
    ("restaurant",                 "Restaurant/Dining"),
    ("food",                       "Food Processing"),
    ("beverage",                   "Beverage (Soft)"),
    ("entertainment",              "Entertainment"),
    ("media",                      "Broadcasting"),
    ("advertising",                "Advertising"),
    ("education",                  "Education"),
    ("e-commerce",                 "Software (Internet)"),
    ("ecommerce",                  "Software (Internet)"),
    ("marketplace",                "Software (Internet)"),
    ("logistics",                  "Transportation"),
    ("transport",                  "Transportation"),
    ("trucking",                   "Trucking"),
    ("aerospace",                  "Aerospace/Defense"),
    ("defense",                    "Aerospace/Defense"),
    ("energy",                     "Power"),
    ("renewable",                  "Green & Renewable Energy"),
    ("oil",                        "Oil/Gas (Production and Exploration)"),
    ("chemical",                   "Chemical (Specialty)"),
    ("mining",                     "Metals & Mining"),
    ("metal",                      "Metals & Mining"),
    ("construction",               "Engineering/Construction"),
    ("engineering",                "Engineering/Construction"),
    ("machinery",                  "Machinery"),
    ("electrical",                 "Electrical Equipment"),
    ("environmental",              "Environmental & Waste Services"),
    ("waste",                      "Environmental & Waste Services"),
    ("agriculture",                "Farming/Agriculture"),
    ("apparel",                    "Apparel"),
    ("shoe",                       "Shoe"),
    ("hotel",                      "Hotel/Gaming"),
    ("gaming",                     "Hotel/Gaming"),
    ("utility",                    "Utility (General)"),
]

# SIC code → Damodaran industry name
# Built from the official SEC SIC code list. SIC codes are authoritative and take
# priority over the keyword-based _SECTOR_MAP when enrich_with_damodaran() runs.
_SIC_DAMODARAN_MAP: dict[str, str] = {
    # ── Agriculture ──────────────────────────────────────────────────────────
    "100":  "Farming/Agriculture",
    "200":  "Farming/Agriculture",
    "700":  "Farming/Agriculture",
    "800":  "Farming/Agriculture",
    "900":  "Farming/Agriculture",
    # ── Mining ───────────────────────────────────────────────────────────────
    "1000": "Metals & Mining",
    "1040": "Precious Metals",
    "1090": "Metals & Mining",
    "1220": "Coal & Related Energy",
    "1221": "Coal & Related Energy",
    "1311": "Oil/Gas (Production and Exploration)",
    "1381": "Oilfield Svcs/Equipment",
    "1382": "Oilfield Svcs/Equipment",
    "1389": "Oilfield Svcs/Equipment",
    "1400": "Metals & Mining",
    # ── Construction ─────────────────────────────────────────────────────────
    "1520": "Engineering/Construction",
    "1531": "Real Estate (Development)",
    "1540": "Engineering/Construction",
    "1600": "Engineering/Construction",
    "1623": "Engineering/Construction",
    "1700": "Engineering/Construction",
    "1731": "Electrical Equipment",
    # ── Food & Beverage ───────────────────────────────────────────────────────
    "2000": "Food Processing",
    "2011": "Food Processing",
    "2013": "Food Processing",
    "2015": "Food Processing",
    "2020": "Food Processing",
    "2024": "Food Processing",
    "2030": "Food Processing",
    "2033": "Food Processing",
    "2040": "Food Processing",
    "2050": "Food Processing",
    "2052": "Food Processing",
    "2060": "Food Processing",
    "2070": "Food Processing",
    "2080": "Beverage (Soft)",
    "2082": "Beverage (Alcoholic)",
    "2086": "Beverage (Soft)",
    "2090": "Food Processing",
    "2092": "Food Processing",
    # ── Tobacco ──────────────────────────────────────────────────────────────
    "2100": "Tobacco",
    "2111": "Tobacco",
    # ── Textiles & Apparel ────────────────────────────────────────────────────
    "2200": "Apparel",
    "2211": "Apparel",
    "2221": "Apparel",
    "2250": "Apparel",
    "2253": "Apparel",
    "2273": "Apparel",
    "2300": "Apparel",
    "2320": "Apparel",
    "2330": "Apparel",
    "2340": "Apparel",
    "2390": "Apparel",
    # ── Lumber, Wood, Furniture ───────────────────────────────────────────────
    "2400": "Paper/Forest Products",
    "2421": "Paper/Forest Products",
    "2430": "Paper/Forest Products",
    "2451": "Engineering/Construction",
    "2452": "Engineering/Construction",
    "2510": "Furn/Home Furnishings",
    "2511": "Furn/Home Furnishings",
    "2520": "Furn/Home Furnishings",
    "2522": "Furn/Home Furnishings",
    "2531": "Furn/Home Furnishings",
    "2540": "Furn/Home Furnishings",
    "2590": "Furn/Home Furnishings",
    # ── Paper & Publishing ────────────────────────────────────────────────────
    "2600": "Paper/Forest Products",
    "2611": "Paper/Forest Products",
    "2621": "Paper/Forest Products",
    "2631": "Paper/Forest Products",
    "2650": "Paper/Forest Products",
    "2670": "Paper/Forest Products",
    "2673": "Paper/Forest Products",
    "2711": "Publishing & Newspapers",
    "2721": "Publishing & Newspapers",
    "2731": "Publishing & Newspapers",
    "2732": "Publishing & Newspapers",
    "2741": "Publishing & Newspapers",
    "2750": "Publishing & Newspapers",
    "2761": "Publishing & Newspapers",
    "2771": "Publishing & Newspapers",
    "2780": "Publishing & Newspapers",
    "2790": "Publishing & Newspapers",
    # ── Chemicals ────────────────────────────────────────────────────────────
    "2800": "Chemical (Specialty)",
    "2810": "Chemical (Basic)",
    "2820": "Chemical (Specialty)",
    "2821": "Chemical (Specialty)",
    "2840": "Household Products",
    "2842": "Household Products",
    "2844": "Household Products",
    "2851": "Chemical (Specialty)",
    "2860": "Chemical (Basic)",
    "2870": "Chemical (Basic)",
    "2890": "Chemical (Specialty)",
    "2891": "Chemical (Specialty)",
    # ── Pharma / Life Sciences ────────────────────────────────────────────────
    "2833": "Drugs (Pharmaceutical)",
    "2834": "Drugs (Pharmaceutical)",
    "2835": "Healthcare Products",
    "2836": "Drugs (Biotechnology)",
    # ── Petroleum ────────────────────────────────────────────────────────────
    "2911": "Oil/Gas (Refining & Marketing)",
    "2950": "Oil/Gas (Refining & Marketing)",
    "2990": "Oil/Gas (Refining & Marketing)",
    # ── Rubber & Plastics ─────────────────────────────────────────────────────
    "3011": "Rubber& Tires",
    "3021": "Shoe",
    "3050": "Chemical (Specialty)",
    "3060": "Chemical (Specialty)",
    "3080": "Chemical (Specialty)",
    "3081": "Chemical (Specialty)",
    "3086": "Chemical (Specialty)",
    "3089": "Chemical (Specialty)",
    # ── Leather & Footwear ────────────────────────────────────────────────────
    "3100": "Apparel",
    "3140": "Shoe",
    # ── Glass, Concrete, Stone ────────────────────────────────────────────────
    "3211": "Engineering/Construction",
    "3220": "Engineering/Construction",
    "3221": "Engineering/Construction",
    "3231": "Engineering/Construction",
    "3241": "Engineering/Construction",
    "3250": "Engineering/Construction",
    "3260": "Engineering/Construction",
    "3270": "Engineering/Construction",
    "3272": "Engineering/Construction",
    "3281": "Engineering/Construction",
    "3290": "Chemical (Specialty)",
    # ── Primary Metals ────────────────────────────────────────────────────────
    "3310": "Steel",
    "3312": "Steel",
    "3317": "Steel",
    "3320": "Steel",
    "3330": "Metals & Mining",
    "3334": "Metals & Mining",
    "3341": "Metals & Mining",
    "3350": "Metals & Mining",
    "3357": "Electrical Equipment",
    "3360": "Metals & Mining",
    "3390": "Metals & Mining",
    # ── Fabricated Metal Products ─────────────────────────────────────────────
    "3411": "Packaging & Container",
    "3412": "Packaging & Container",
    "3420": "Machinery",
    "3430": "Machinery",
    "3433": "Machinery",
    "3440": "Engineering/Construction",
    "3442": "Engineering/Construction",
    "3443": "Machinery",
    "3444": "Machinery",
    "3448": "Engineering/Construction",
    "3451": "Machinery",
    "3452": "Machinery",
    "3460": "Machinery",
    "3470": "Machinery",
    "3480": "Aerospace/Defense",
    "3490": "Machinery",
    # ── Industrial Machinery ──────────────────────────────────────────────────
    "3510": "Machinery",
    "3523": "Machinery",
    "3524": "Machinery",
    "3530": "Machinery",
    "3531": "Machinery",
    "3532": "Machinery",
    "3533": "Oilfield Svcs/Equipment",
    "3537": "Machinery",
    "3540": "Machinery",
    "3541": "Machinery",
    "3550": "Machinery",
    "3555": "Machinery",
    "3559": "Machinery",
    "3560": "Machinery",
    "3561": "Machinery",
    "3562": "Machinery",
    "3564": "Machinery",
    "3567": "Machinery",
    "3569": "Machinery",
    "3580": "Machinery",
    "3585": "Machinery",
    "3590": "Machinery",
    # ── Computer & Office Equipment ───────────────────────────────────────────
    "3570": "Computer Services",
    "3571": "Computer Services",
    "3572": "Computer Services",
    "3575": "Computer Services",
    "3576": "Telecom. Equipment",
    "3577": "Computer Services",
    "3578": "Computer Services",
    "3579": "Computer Services",
    # ── Electronics ───────────────────────────────────────────────────────────
    "3600": "Electronics (General)",
    "3612": "Electrical Equipment",
    "3613": "Electrical Equipment",
    "3620": "Electrical Equipment",
    "3621": "Electrical Equipment",
    "3630": "Electronics (Consumer & Office)",
    "3634": "Electronics (Consumer & Office)",
    "3640": "Electrical Equipment",
    "3651": "Electronics (Consumer & Office)",
    "3652": "Entertainment",
    "3661": "Telecom. Equipment",
    "3663": "Telecom. Equipment",
    "3669": "Telecom. Equipment",
    "3670": "Electronics (General)",
    "3672": "Semiconductor",
    "3674": "Semiconductor",
    "3677": "Electronics (General)",
    "3678": "Electronics (General)",
    "3679": "Electronics (General)",
    "3690": "Electronics (General)",
    "3695": "Electronics (General)",
    # ── Transportation Equipment ──────────────────────────────────────────────
    "3711": "Auto & Truck",
    "3713": "Auto & Truck",
    "3714": "Auto Parts",
    "3715": "Auto Parts",
    "3716": "Auto & Truck",
    "3720": "Aerospace/Defense",
    "3721": "Aerospace/Defense",
    "3724": "Aerospace/Defense",
    "3728": "Aerospace/Defense",
    "3730": "Shipbuilding & Marine",
    "3743": "Transportation (Railroads)",
    "3751": "Machinery",
    "3760": "Aerospace/Defense",
    "3790": "Transportation",
    # ── Instruments & Medical Devices ─────────────────────────────────────────
    "3812": "Aerospace/Defense",
    "3821": "Healthcare Products",
    "3822": "Electrical Equipment",
    "3823": "Electrical Equipment",
    "3824": "Electronics (General)",
    "3825": "Electrical Equipment",
    "3826": "Healthcare Products",
    "3827": "Electronics (General)",
    "3829": "Electrical Equipment",
    "3841": "Healthcare Products",
    "3842": "Healthcare Products",
    "3843": "Healthcare Products",
    "3844": "Healthcare Products",
    "3845": "Healthcare Products",
    "3851": "Healthcare Products",
    "3861": "Electronics (General)",
    "3873": "Electronics (Consumer & Office)",
    # ── Miscellaneous Manufacturing ───────────────────────────────────────────
    "3910": "Furn/Home Furnishings",
    "3911": "Furn/Home Furnishings",
    "3931": "Recreation",
    "3942": "Recreation",
    "3944": "Recreation",
    "3949": "Recreation",
    "3950": "Office Equipment & Services",
    "3960": "Furn/Home Furnishings",
    "3990": "Machinery",
    # ── Railroads ─────────────────────────────────────────────────────────────
    "4011": "Transportation (Railroads)",
    "4013": "Transportation (Railroads)",
    # ── Local Transit & Trucking ──────────────────────────────────────────────
    "4100": "Transportation",
    "4210": "Trucking",
    "4213": "Trucking",
    "4220": "Transportation",
    "4231": "Transportation",
    # ── Water & Air Transport ─────────────────────────────────────────────────
    "4400": "Shipbuilding & Marine",
    "4412": "Shipbuilding & Marine",
    "4512": "Air Transport",
    "4513": "Air Transport",
    "4522": "Air Transport",
    "4581": "Air Transport",
    # ── Pipeline & Other Transport ────────────────────────────────────────────
    "4610": "Oil/Gas Distribution",
    "4700": "Transportation",
    "4731": "Transportation",
    # ── Telecom ───────────────────────────────────────────────────────────────
    "4812": "Telecom (Wireless)",
    "4813": "Telecom. Services",
    "4822": "Telecom. Services",
    "4832": "Broadcasting",
    "4833": "Broadcasting",
    "4841": "Entertainment",
    "4899": "Telecom. Services",
    # ── Utilities ─────────────────────────────────────────────────────────────
    "4900": "Utility (General)",
    "4911": "Power",
    "4922": "Utility (General)",
    "4923": "Utility (General)",
    "4924": "Utility (General)",
    "4931": "Utility (General)",
    "4932": "Utility (General)",
    "4941": "Utility (Water)",
    "4950": "Environmental & Waste Services",
    "4953": "Environmental & Waste Services",
    "4955": "Environmental & Waste Services",
    "4961": "Utility (General)",
    "4991": "Green & Renewable Energy",
    # ── Wholesale Trade ───────────────────────────────────────────────────────
    "5000": "Retail (Distributors)",
    "5010": "Retail (Automotive)",
    "5013": "Retail (Automotive)",
    "5020": "Furn/Home Furnishings",
    "5030": "Engineering/Construction",
    "5031": "Engineering/Construction",
    "5040": "Office Equipment & Services",
    "5045": "Computer Services",
    "5047": "Healthcare Products",
    "5050": "Metals & Mining",
    "5051": "Metals & Mining",
    "5063": "Electrical Equipment",
    "5064": "Electronics (Consumer & Office)",
    "5065": "Electronics (General)",
    "5070": "Machinery",
    "5072": "Machinery",
    "5080": "Machinery",
    "5082": "Machinery",
    "5084": "Machinery",
    "5090": "Retail (Distributors)",
    "5094": "Furn/Home Furnishings",
    "5099": "Retail (Distributors)",
    "5110": "Paper/Forest Products",
    "5122": "Drugs (Pharmaceutical)",
    "5130": "Apparel",
    "5140": "Food Wholesalers",
    "5141": "Food Wholesalers",
    "5150": "Farming/Agriculture",
    "5160": "Chemical (Specialty)",
    "5171": "Oil/Gas Distribution",
    "5172": "Oil/Gas Distribution",
    "5180": "Beverage (Alcoholic)",
    "5190": "Retail (Distributors)",
    # ── Retail Trade ──────────────────────────────────────────────────────────
    "5200": "Retail (Building Supply)",
    "5211": "Retail (Building Supply)",
    "5271": "Retail (General)",
    "5311": "Retail (General)",
    "5331": "Retail (General)",
    "5399": "Retail (General)",
    "5400": "Retail (Grocery and Food)",
    "5411": "Retail (Grocery and Food)",
    "5412": "Retail (Grocery and Food)",
    "5500": "Retail (Automotive)",
    "5531": "Retail (Automotive)",
    "5600": "Apparel",
    "5621": "Apparel",
    "5651": "Apparel",
    "5661": "Shoe",
    "5700": "Furn/Home Furnishings",
    "5712": "Furn/Home Furnishings",
    "5731": "Electronics (Consumer & Office)",
    "5734": "Retail (Online)",
    "5735": "Entertainment",
    "5810": "Restaurant/Dining",
    "5812": "Restaurant/Dining",
    "5900": "Retail (Special Lines)",
    "5912": "Retail (Special Lines)",
    "5940": "Retail (Special Lines)",
    "5944": "Retail (Special Lines)",
    "5945": "Retail (Special Lines)",
    "5960": "Retail (Online)",
    "5961": "Retail (Online)",
    "5990": "Retail (Special Lines)",
    # ── Finance ───────────────────────────────────────────────────────────────
    "6021": "Banks (Regional)",
    "6022": "Banks (Regional)",
    "6029": "Banks (Regional)",
    "6035": "Banks (Regional)",
    "6036": "Banks (Regional)",
    "6099": "Financial Svcs. (Non-bank & Insurance)",
    "6111": "Financial Svcs. (Non-bank & Insurance)",
    "6141": "Financial Svcs. (Non-bank & Insurance)",
    "6153": "Financial Svcs. (Non-bank & Insurance)",
    "6159": "Financial Svcs. (Non-bank & Insurance)",
    "6162": "Financial Svcs. (Non-bank & Insurance)",
    "6163": "Financial Svcs. (Non-bank & Insurance)",
    "6172": "Financial Svcs. (Non-bank & Insurance)",
    "6189": "Financial Svcs. (Non-bank & Insurance)",
    "6199": "Financial Svcs. (Non-bank & Insurance)",
    "6200": "Brokerage & Investment Banking",
    "6211": "Brokerage & Investment Banking",
    "6221": "Brokerage & Investment Banking",
    "6282": "Investments & Asset Management",
    "6311": "Insurance (Life)",
    "6321": "Insurance (General)",
    "6324": "Insurance (General)",
    "6331": "Insurance (Prop/Cas.)",
    "6351": "Insurance (General)",
    "6361": "Insurance (General)",
    "6399": "Insurance (General)",
    "6411": "Insurance (General)",
    # ── Real Estate ───────────────────────────────────────────────────────────
    "6500": "Real Estate (General/Diversified)",
    "6510": "Real Estate (Operations & Services)",
    "6512": "Real Estate (Operations & Services)",
    "6513": "Real Estate (Operations & Services)",
    "6519": "Real Estate (Operations & Services)",
    "6531": "Real Estate (Operations & Services)",
    "6532": "Real Estate (Development)",
    "6552": "Real Estate (Development)",
    "6792": "Oil/Gas (Production and Exploration)",
    "6794": "Financial Svcs. (Non-bank & Insurance)",
    "6795": "Metals & Mining",
    "6798": "R.E.I.T.",
    "6799": "Investments & Asset Management",
    # ── Hotels & Lodging ──────────────────────────────────────────────────────
    "7000": "Hotel/Gaming",
    "7011": "Hotel/Gaming",
    # ── Business Services ─────────────────────────────────────────────────────
    "7200": "Business & Consumer Services",
    "7310": "Advertising",
    "7311": "Advertising",
    "7320": "Financial Svcs. (Non-bank & Insurance)",
    "7330": "Advertising",
    "7331": "Advertising",
    "7340": "Business & Consumer Services",
    "7350": "Financial Svcs. (Non-bank & Insurance)",
    "7359": "Financial Svcs. (Non-bank & Insurance)",
    "7361": "Business & Consumer Services",
    "7363": "Business & Consumer Services",
    # ── Software & Technology Services ───────────────────────────────────────
    "7370": "Software (System & Application)",
    "7371": "Software (System & Application)",
    "7372": "Software (System & Application)",
    "7373": "Software (System & Application)",
    "7374": "Computer Services",
    "7377": "Computer Services",
    "7380": "Business & Consumer Services",
    "7381": "Business & Consumer Services",
    "7384": "Business & Consumer Services",
    "7385": "Telecom. Services",
    "7389": "Business & Consumer Services",
    # ── Auto & Miscellaneous Services ─────────────────────────────────────────
    "7500": "Business & Consumer Services",
    "7510": "Financial Svcs. (Non-bank & Insurance)",
    "7600": "Business & Consumer Services",
    # ── Entertainment & Recreation ────────────────────────────────────────────
    "7812": "Entertainment",
    "7819": "Entertainment",
    "7822": "Entertainment",
    "7829": "Entertainment",
    "7830": "Entertainment",
    "7841": "Entertainment",
    "7900": "Recreation",
    "7948": "Hotel/Gaming",
    "7990": "Recreation",
    "7997": "Recreation",
    # ── Healthcare Services ───────────────────────────────────────────────────
    "8000": "Hospitals/Healthcare Facilities",
    "8011": "Hospitals/Healthcare Facilities",
    "8050": "Hospitals/Healthcare Facilities",
    "8051": "Hospitals/Healthcare Facilities",
    "8060": "Hospitals/Healthcare Facilities",
    "8062": "Hospitals/Healthcare Facilities",
    "8071": "Healthcare Support Services",
    "8082": "Healthcare Support Services",
    "8090": "Healthcare Support Services",
    "8093": "Hospitals/Healthcare Facilities",
    # ── Professional & Educational Services ──────────────────────────────────
    "8111": "Business & Consumer Services",
    "8200": "Education",
    "8300": "Business & Consumer Services",
    "8351": "Education",
    "8600": "Business & Consumer Services",
    "8700": "Engineering/Construction",
    "8711": "Engineering/Construction",
    "8731": "Business & Consumer Services",
    "8734": "Business & Consumer Services",
    "8741": "Business & Consumer Services",
    "8742": "Business & Consumer Services",
    "8744": "Business & Consumer Services",
    "8900": "Business & Consumer Services",
}


def _fetch_damodaran_table(url: str, value_col_hint: str) -> dict[str, float]:
    """
    Fetch a Damodaran HTML table and return {industry_name: float_value}.
    value_col_hint is a lowercase substring that identifies the target column header.
    """
    r = requests.get(url, headers={"User-Agent": "IPO-Screener research@yourfirm.com"}, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table")
    if not table:
        return {}

    rows = table.find_all("tr")
    if not rows:
        return {}

    # Find the header row and locate the target column index
    # Normalize headers: collapse internal whitespace so newlines don't break matching
    header_row = rows[0]
    headers = [
        " ".join(th.get_text().split()).lower()
        for th in header_row.find_all(["th", "td"])
    ]
    col_idx = next(
        (i for i, h in enumerate(headers) if value_col_hint in h),
        None,
    )
    if col_idx is None:
        return {}

    result = {}
    for row in rows[1:]:
        cells = row.find_all(["td", "th"])
        if len(cells) <= col_idx:
            continue
        # Normalize industry name — collapse internal whitespace (Damodaran uses line breaks)
        industry = " ".join(cells[0].get_text().split())
        raw_val  = cells[col_idx].get_text(strip=True).replace(",", "")
        try:
            val = float(raw_val)
            result[industry] = val
        except ValueError:
            pass
    return result


def _load_damodaran_cache() -> dict:
    """Fetch (or return cached) Damodaran EV/EBITDA and EV/Sales tables."""
    global _damodaran_cache
    if _damodaran_cache is not None:
        return _damodaran_cache

    log.info("Fetching Damodaran industry multiples (January 2026)...")
    ev_ebitda: dict[str, float] = {}
    ev_sales:  dict[str, float] = {}

    try:
        ev_ebitda = _fetch_damodaran_table(
            "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/vebitda.html",
            "ev/ebitda",
        )
        time.sleep(0.5)
        ev_sales = _fetch_damodaran_table(
            "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/psdata.html",
            "ev/sales",
        )
        log.info(f"Damodaran: loaded {len(ev_ebitda)} EV/EBITDA rows, {len(ev_sales)} EV/Sales rows")
    except Exception as e:
        log.warning(f"Damodaran fetch failed: {e}")

    p_b: dict[str, float] = {}
    p_e: dict[str, float] = {}
    try:
        time.sleep(0.5)
        p_b = _fetch_damodaran_table(
            "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/pbvdata.html",
            "pbv",
        )
        time.sleep(0.5)
        p_e = _fetch_damodaran_table(
            "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/pedata.html",
            "current pe",
        )
        log.info(f"Damodaran: loaded {len(p_b)} P/B rows, {len(p_e)} P/E rows")
    except Exception as e:
        log.warning(f"Damodaran P/B and P/E fetch failed: {e}")

    _damodaran_cache = {"ev_ebitda": ev_ebitda, "ev_sales": ev_sales, "p_b": p_b, "p_e": p_e}
    return _damodaran_cache


def _match_damodaran_industry(sector: str, subsector: str, sic_code: str = "") -> str | None:
    """
    Match a company's sector to the closest Damodaran industry name.
    Priority: (1) SIC code lookup — authoritative; (2) keyword match on sector/subsector text.
    Returns the matched industry name, or None if no match found.
    """
    if sic_code:
        mapped = _SIC_DAMODARAN_MAP.get(str(sic_code).strip())
        if mapped:
            log.info(f"Damodaran: SIC {sic_code} → '{mapped}'")
            return mapped
    combined = f"{sector} {subsector}".lower()
    for keyword, industry in _SECTOR_MAP:
        if keyword in combined:
            return industry
    return None


def enrich_with_damodaran(memo: dict) -> dict:
    """
    Add damodaran_comps section to a memo by matching the company's sector
    to Damodaran's publicly available January 2026 industry multiples.

    Sets:
      memo["damodaran_comps"]["matched_industry"]
      memo["damodaran_comps"]["ev_ebitda_sector_median"]
      memo["damodaran_comps"]["ev_revenue_sector_median"]

    Also updates valuation.sector_median_ev_revenue if not already set by yfinance.
    Falls back gracefully on any error.
    """
    sector    = memo.get("sector", "") or ""
    subsector = memo.get("subsector", "") or ""
    sic_code  = memo.get("sic_code", "") or ""

    industry = _match_damodaran_industry(sector, subsector, sic_code)
    if not industry:
        log.info(f"Damodaran: no industry match for SIC='{sic_code}' sector='{sector}' subsector='{subsector}'")
        return memo

    try:
        cache     = _load_damodaran_cache()
        ev_ebitda = cache["ev_ebitda"].get(industry)
        ev_sales  = cache["ev_sales"].get(industry)
        p_b_val   = cache.get("p_b", {}).get(industry)
        p_e_val   = cache.get("p_e", {}).get(industry)

        val            = memo.get("valuation") or {}
        sector_class   = (val.get("sector_classification") or "").lower()

        # Select primary benchmark metric based on sector classification
        if sector_class in ("bank", "fintech_balance_sheet", "insurance"):
            primary_bm   = "P/B"
            primary_bv   = p_b_val
        elif sector_class == "asset_manager":
            primary_bm   = "P/E"
            primary_bv   = p_e_val
        elif sector_class in ("lease_heavy",):
            # Damodaran does not publish EV/EBITDAR; show EV/EBITDA as proxy
            primary_bm   = "EV/EBITDAR (EV/EBITDA shown as Damodaran proxy)"
            primary_bv   = ev_ebitda
        elif sector_class == "multi_segment_sotp":
            primary_bm   = "Multiple (SOTP — segment-specific)"
            primary_bv   = None
        else:
            primary_bm   = "EV/EBITDA"
            primary_bv   = ev_ebitda

        memo["damodaran_comps"] = {
            "matched_industry":           industry,
            "ev_ebitda_sector_median":    ev_ebitda,
            "ev_revenue_sector_median":   ev_sales,
            "p_b_sector_median":          p_b_val,
            "p_e_sector_median":          p_e_val,
            "primary_benchmark_metric":   primary_bm,
            "primary_benchmark_value":    primary_bv,
            "source":      "Damodaran NYU Stern (January 2026)",
            "source_urls": [
                "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/vebitda.html",
                "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/psdata.html",
                "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/pbvdata.html",
                "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/pedata.html",
            ],
        }

        # Back-fill valuation.sector_median_ev_revenue if yfinance didn't set it
        if ev_sales and not val.get("sector_median_ev_revenue"):
            val["sector_median_ev_revenue"] = ev_sales
            val["sector_median_source"]     = "damodaran"
            subject_ev_rev = val.get("ev_revenue_multiple")
            if subject_ev_rev and ev_sales:
                val["premium_to_sector_median_pct"] = round(
                    (subject_ev_rev - ev_sales) / ev_sales * 100
                )
                if subject_ev_rev > 2 * ev_sales:
                    val["valuation_flag"] = True
            memo["valuation"] = val

        log.info(
            f"Damodaran: matched '{industry}' — "
            f"EV/EBITDA={ev_ebitda}x, EV/Revenue={ev_sales}x, "
            f"primary_benchmark={primary_bm} ({primary_bv})"
        )
    except Exception as e:
        log.warning(f"Damodaran enrichment failed: {e}")

    return memo


def enrich_valuation_with_live_comps(memo: dict) -> dict:
    """
    Fetch live EV/Revenue multiples for the public comps Claude identified.
    Requires: pip install yfinance

    - Pulls market cap, enterprise value, and TTM revenue for each ticker.
    - Recalculates sector_median_ev_revenue from live data.
    - Recalculates premium_to_sector_median_pct if subject EV/Revenue is available.
    - Adds valuation.live_comps_data[] with per-ticker detail for the app to display.
    - Falls back gracefully if yfinance is not installed or data is unavailable.
    """
    try:
        import yfinance as yf
    except ImportError:
        log.info("yfinance not installed — skipping live comp enrichment (pip install yfinance to enable)")
        return memo

    val = memo.get("valuation")
    if not val:
        return memo

    # Support both legacy public_comps and modern comparable_companies field names
    raw_comps = val.get("public_comps") or val.get("comparable_companies", [])
    if not raw_comps:
        return memo

    # Support both string-array (legacy) and object-array (new /comps format)
    # Build a lookup of existing comps by ticker so we can merge live data in
    comp_objects = {}   # ticker → object (from /comps pre-fetch or Opus-generated)
    tickers = []
    for c in raw_comps:
        if isinstance(c, str):
            t = c.strip().upper()
            if 1 <= len(t) <= 10:
                tickers.append(t)
                comp_objects[t] = {"ticker": t, "name": t}
        elif isinstance(c, dict):
            t = (c.get("ticker") or "").strip().upper()
            if 1 <= len(t) <= 10:
                tickers.append(t)
                comp_objects[t] = c   # preserve all existing fields (ev_revenue, etc.)
    tickers = tickers[:6]  # cap at 6

    if not tickers:
        return memo

    log.info(f"Fetching live comp data for: {', '.join(tickers)}")
    live_comps = []
    ev_revenue_multiples = []

    for ticker in tickers:
        try:
            info   = yf.Ticker(ticker).info
            ev     = info.get("enterpriseValue")
            rev    = info.get("totalRevenue")
            ebitda = info.get("ebitda")
            growth = info.get("revenueGrowth")
            name   = info.get("shortName", comp_objects.get(ticker, {}).get("name", ticker))
            ev_rev = ev_ebitda = rev_grow = None
            if ev and rev and rev > 0:
                ev_rev = round(ev / rev, 1)
                ev_revenue_multiples.append(ev_rev)
            if ev and ebitda and ebitda > 0:
                ev_ebitda = round(ev / ebitda, 1)
            if growth is not None:
                rev_grow = round(growth * 100, 1)

            # Merge live data into the existing comp object, preferring live values
            base = comp_objects.get(ticker, {})
            live_comps.append({
                **base,
                "ticker":               ticker,
                "name":                 name,
                "ev_usd_millions":      round(ev / 1_000_000) if ev else None,
                "revenue_ttm_usd_millions": round(rev / 1_000_000) if rev else None,
                "ev_revenue_multiple":  ev_rev   if ev_rev   is not None else base.get("ev_revenue"),
                "ev_ebitda_multiple":   ev_ebitda if ev_ebitda is not None else base.get("ev_ebitda"),
                "revenue_growth_pct":   rev_grow  if rev_grow  is not None else base.get("revenue_growth_pct"),
            })
            time.sleep(0.3)  # yfinance rate limiting
        except Exception as e:
            log.warning(f"Could not fetch comp data for {ticker}: {e}")
            # Preserve the comp object without live enrichment rather than silently dropping
            base = comp_objects.get(ticker, {"ticker": ticker, "name": ticker})
            live_comps.append({**base, "ev_usd_millions": None, "revenue_ttm_usd_millions": None})

    if not live_comps:
        return memo

    val["live_comps_data"] = live_comps

    # Enrich Section 16 comparable IPO entries: validate, fetch current price,
    # and auto-compute current_vs_ipo_pct from stored ipo_price.
    # Supports both legacy memo.comparable_ipos and modern
    # memo.comparable_ipo_performance.comparable_ipos storage paths.
    _cip = memo.get("comparable_ipo_performance") or {}
    raw_ipos = (
        _cip.get("comparable_ipos")
        or _cip.get("recent_comps")
        or memo.get("comparable_ipos")
        or []
    )
    if raw_ipos:
        valid_ipos = []
        for comp in raw_ipos:
            ticker = (comp.get("ticker") or "").strip().upper()
            if not ticker:
                valid_ipos.append(comp)
                continue
            try:
                info        = yf.Ticker(ticker).info
                mc          = info.get("marketCap")
                ev          = info.get("enterpriseValue")
                current_px  = info.get("currentPrice") or info.get("regularMarketPrice")
                if not mc and not ev:
                    log.warning(f"Section 16 comp {ticker} dropped — no market cap or EV returned")
                    continue
                # Auto-compute current_vs_ipo_pct when ipo_price is stored
                ipo_px = comp.get("ipo_price") or comp.get("offer_price")
                if current_px and ipo_px and ipo_px > 0:
                    comp = {**comp, "current_vs_ipo_pct": round((current_px - ipo_px) / ipo_px * 100, 1)}
                    log.info(f"Section 16 {ticker}: ${ipo_px} → ${current_px} ({comp['current_vs_ipo_pct']:+.1f}%)")
                valid_ipos.append(comp)
                time.sleep(0.3)
            except Exception as e:
                log.warning(f"Section 16 comp {ticker} — yfinance error: {e}")
                valid_ipos.append(comp)  # keep with existing data rather than dropping
        # Write back to whichever path the memo uses
        if _cip.get("comparable_ipos") is not None or _cip.get("recent_comps") is not None:
            _cip["comparable_ipos"] = valid_ipos
            memo["comparable_ipo_performance"] = _cip
        else:
            memo["comparable_ipos"] = valid_ipos

    if ev_revenue_multiples:
        sorted_multiples = sorted(ev_revenue_multiples)
        median = sorted_multiples[len(sorted_multiples) // 2]
        val["sector_median_ev_revenue"] = median
        val["sector_median_source"] = "live_market_data"
        # Recalculate premium if we have subject EV/Revenue
        subject_ev_rev = val.get("ev_revenue_multiple")
        if subject_ev_rev and median:
            val["premium_to_sector_median_pct"] = round(
                (subject_ev_rev - median) / median * 100
            )
        # Update valuation_flag based on live data (>2x sector median = flag)
        if subject_ev_rev and median and subject_ev_rev > 2 * median:
            val["valuation_flag"] = True

    memo["valuation"] = val
    memo["live_comps_enriched"] = True
    log.info(
        f"Live comp enrichment complete: {len(live_comps)} comps, "
        f"median EV/Rev: {val.get('sector_median_ev_revenue')}x"
    )
    return memo


def _derive_recommendation(wt: float) -> str:
    """Derive recommendation band from weighted_total using current thresholds."""
    if wt >= 75:
        return "UNDERWRITE"
    elif wt >= 65:
        return "CONDITIONAL_LIGHT"
    elif wt >= 55:
        return "CONDITIONAL_HEAVY"
    else:
        return "PASS"


def apply_leverage_adjustments(memo: dict) -> dict:
    """
    Detect leveraged issuers and reweight Financial Health / Valuation dimensions.

    Leveraged issuer criteria:
      - GAAP-profitable (net_income >= 0): Debt/Adj.EBITDA > 4x
      - GAAP-loss        (net_income <  0): Debt/Adj.EBITDA > 5x
    When triggered: FHR weight 15%→20%, VA weight 20%→15%.
    Recalculates weighted_total. Sets leveraged_issuer_flag: true.
    """
    scores = memo.get("scores") or {}
    fin    = memo.get("financials") or {}
    if not all(k in scores for k in ("business_model_quality", "financial_health_runway",
                                      "market_competitive_position", "management_governance",
                                      "valuation_attractiveness")):
        return memo

    total_debt = fin.get("total_debt_usd_millions") or 0
    ebitda     = fin.get("ebitda_usd_millions")
    net_income = fin.get("net_income_usd_millions")

    if not ebitda or ebitda <= 0 or total_debt <= 0:
        return memo  # can't compute leverage ratio

    leverage_ratio = total_debt / ebitda
    is_gaap_loss   = (net_income is not None and net_income < 0)
    threshold      = 5.0 if is_gaap_loss else 4.0

    if leverage_ratio <= threshold:
        return memo  # not a leveraged issuer

    memo["leveraged_issuer_flag"] = True
    fhr_w, va_w = 0.20, 0.15

    bmq = scores.get("business_model_quality") or 0
    fhr = scores.get("financial_health_runway") or 0
    mcp = scores.get("market_competitive_position") or 0
    mg  = scores.get("management_governance") or 0
    va  = scores.get("valuation_attractiveness") or 0

    new_wt = round((bmq * 0.25 + fhr * fhr_w + mcp * 0.20 + mg * 0.20 + va * va_w) * 10, 1)
    adj_list = scores.get("adjustments") or []
    adj_list.append({
        "rule":    "Leverage reweight",
        "detail":  f"Debt/EBITDA {leverage_ratio:.1f}x — FHR weight 15%→20%, VA weight 20%→15%",
        "penalty": round(new_wt - (scores.get("weighted_total") or 0), 1),
    })
    scores["weighted_total"]  = new_wt
    scores["fhr_weight_used"] = fhr_w
    scores["va_weight_used"]  = va_w
    scores["adjustments"]     = adj_list
    memo["scores"]            = scores
    log.info(
        f"Leveraged issuer detected ({leverage_ratio:.1f}x D/EBITDA) — "
        f"FHR/VA reweighted, new score: {new_wt}"
    )
    return memo


def apply_leverage_floor(memo: dict) -> dict:
    """
    Detect high-leverage conditions and note them for analyst review.

    Previously applied a hard cap to FHR at 4.0 — that behavior is removed.
    The function now only detects the threshold and adds a note to adjustments
    (without modifying any dimension score or weighted_total). Opus is instructed
    to populate leverage_assessment when this condition is present.

    Detection thresholds (unchanged):
      - GAAP-profitable + Debt/EBITDA > 4x
      - GAAP-loss + Debt/AdjEBITDA > 6x AND interest_expense > 20% of revenue
    """
    scores = memo.get("scores") or {}
    fin    = memo.get("financials") or {}
    fhr    = scores.get("financial_health_runway")

    total_debt = fin.get("total_debt_usd_millions") or 0
    ebitda     = fin.get("ebitda_usd_millions")
    net_income = fin.get("net_income_usd_millions")
    rev        = (fin.get("revenue_ttm_usd_millions")
                  or (fin.get("revenue_usd_millions") or {}).get("ttm"))

    if not ebitda or ebitda <= 0 or total_debt <= 0:
        return memo

    leverage_ratio = total_debt / ebitda
    is_gaap_loss   = (net_income is not None and net_income < 0)
    threshold_met  = False

    if not is_gaap_loss and leverage_ratio > 4.0:
        threshold_met = True
    elif is_gaap_loss and leverage_ratio > 6.0:
        interest = fin.get("interest_expense_usd_millions")
        if interest and rev and rev > 0 and (interest / rev) > 0.20:
            threshold_met = True

    if not threshold_met:
        return memo

    # Note the condition without capping any score
    adj_list = list(scores.get("adjustments") or [])
    adj_list.append({
        "rule":    "Leverage threshold detected",
        "detail":  (f"D/EBITDA {leverage_ratio:.1f}x — exceeds threshold "
                    f"({'4x profitable' if not is_gaap_loss else '6x + interest >20% rev'}). "
                    f"See leverage_assessment for strategic evaluation. No FHR cap applied."),
        "penalty": 0,
    })
    scores["adjustments"] = adj_list
    memo["scores"]        = scores
    log.info(
        f"Leverage threshold detected ({leverage_ratio:.1f}x D/EBITDA) — "
        f"noted in adjustments, no score cap applied"
    )
    return memo


# ─────────────────────────────────────────────────────────────────────────────
# SECTOR-SPECIFIC VALUATION METRIC SELECTION
# ─────────────────────────────────────────────────────────────────────────────

def select_valuation_metric(
    sic_code: str,
    gaap_profitable: bool,
    business_model_description: str,
    segment_count: int,
    lease_intensity_pct,
    capex_intensity_pct,
) -> dict:
    """
    Select the primary and secondary valuation metric combination for a company
    based on its SIC code, profitability, business model, and capital intensity.

    Returns a dict with keys:
        primary_metric, secondary_metric, methodology_rationale, sector_classification

    Priority order:
      Step 1 — SOTP override: segment_count >= 2 always wins
      Step 2 — Financial services sub-router (banks, insurance, fintech)
      Step 3 — Non-financial sector overrides (O&G E&P, lease-heavy, capex-intensive, biotech)
      Step 4 — Default profitability-based (EV/EBITDA for profitable, EV/Revenue for loss)
      Step 5 — Tech secondary metric appendage (SaaS subscribers, MAU, GMV)
    """
    sic  = str(sic_code).strip()
    bmd  = (business_model_description or "").lower()

    # ── Step 1: SOTP override for materially distinct multi-segment companies ──
    if segment_count >= 2:
        return {
            "primary_metric":       "SOTP",
            "secondary_metric":     "EV/EBITDA",
            "methodology_rationale": (
                "Multi-segment company with distinct operating divisions; "
                "Sum-of-the-Parts is the primary methodology to avoid conglomerate "
                "discount distortion. Each segment is benchmarked on its own natural "
                "metric; consolidated EV/EBITDA is shown as a secondary cross-check."
            ),
            "sector_classification": "multi_segment_sotp",
        }

    # ── Step 2: Financial services sub-router ────────────────────────────────
    if sic in ("6020", "6021", "6022"):
        return {
            "primary_metric":       "P/B",
            "secondary_metric":     "P/TBV",
            "methodology_rationale": (
                "Commercial bank; P/Book and P/Tangible Book Value are the institutional "
                "standard, anchored to capital adequacy (CET1) and ROE/ROTCE delivery. "
                "EV/EBITDA is not meaningful for banks."
            ),
            "sector_classification": "bank",
        }

    if sic in ("6311", "6321", "6331"):
        return {
            "primary_metric":       "P/B",
            "secondary_metric":     "P/E",
            "methodology_rationale": (
                "Insurance underwriter; P/Book reflects reserve adequacy and capital "
                "strength. P&C lines pair P/B with combined ratio; life lines use "
                "embedded value methodology as secondary cross-check."
            ),
            "sector_classification": "insurance",
        }

    if sic in ("6411",):
        return {
            "primary_metric":       "EV/EBITDA",
            "secondary_metric":     "P/E",
            "methodology_rationale": (
                "Insurance broker with fee-based recurring commissions; EV/EBITDA "
                "is standard for asset-light distribution businesses with stable "
                "margin profiles, aligning with public broker comps."
            ),
            "sector_classification": "insurance_broker",
        }

    if sic in ("6282",):
        return {
            "primary_metric":       "P/E",
            "secondary_metric":     "EV/AUM",
            "methodology_rationale": (
                "Asset manager; P/E captures fee-based earnings yield on a multiple "
                "that normalizes across strategies, while EV/AUM benchmarks peers on "
                "total assets managed."
            ),
            "sector_classification": "asset_manager",
        }

    # Fintech sub-router — critical: Chime-style platforms use EV/Revenue even
    # though SIC may land in financial services range
    if sic in ("6199", "6141", "6029"):
        balance_sheet_terms = (
            "deposit", "chartered bank", "lending on balance sheet",
            "loan portfolio", "interest income from loans"
        )
        if any(t in bmd for t in balance_sheet_terms):
            return {
                "primary_metric":       "P/B",
                "secondary_metric":     "P/TBV",
                "methodology_rationale": (
                    "Chartered neobank or digital lender with a material loan book; "
                    "P/Book and P/Tangible Book reflect credit portfolio risk, consistent "
                    "with bank-sector comparable methodology. Note: a fintech platform "
                    "without a material loan book (e.g. Chime) uses EV/Revenue instead."
                ),
                "sector_classification": "fintech_balance_sheet",
            }
        else:
            return {
                "primary_metric":       "EV/Revenue",
                "secondary_metric":     "EV/Gross Profit",
                "methodology_rationale": (
                    "Fee-based fintech platform with no material loan book; EV/Revenue "
                    "and EV/Gross Profit are standard for software-like financial services "
                    "companies. Despite SIC classification in the financial services range, "
                    "these platforms trade on tech multiples, not book-value multiples."
                ),
                "sector_classification": "fintech_services",
            }

    # ── Step 3: Non-financial sector overrides ────────────────────────────────
    if sic in ("1311", "1381"):
        return {
            "primary_metric":       "EV/EBITDAX",
            "secondary_metric":     "NAV (PV-10)",
            "methodology_rationale": (
                "Oil & gas E&P; EV/EBITDAX normalizes across varying exploration expense "
                "levels. Reserve-based NAV using PV-10 (10% discount rate) is the "
                "institutional secondary for production and reserves valuation."
            ),
            "sector_classification": "oil_gas_e_and_p",
        }

    if lease_intensity_pct is not None and lease_intensity_pct >= 15:
        return {
            "primary_metric":       "EV/EBITDAR",
            "secondary_metric":     "EV/EBITDA",
            "methodology_rationale": (
                f"Lease-intensive business ({lease_intensity_pct:.1f}% rent/revenue); "
                "EV/EBITDAR adds rent back to normalize across own-vs.-lease real estate "
                "strategies, standard for hospitality, restaurants, airlines, and "
                "transportation operators."
            ),
            "sector_classification": "lease_heavy",
        }

    if capex_intensity_pct is not None and capex_intensity_pct >= 12:
        return {
            "primary_metric":       "EV/(EBITDA-Capex)",
            "secondary_metric":     "EV/EBITDA",
            "methodology_rationale": (
                f"Capex-intensive business ({capex_intensity_pct:.1f}% capex/revenue ≥12% threshold); "
                "EV/(EBITDA-Capex) reflects true free cash flow generation capacity and "
                "maintenance capex burden, more informative than headline EBITDA multiples "
                "for heavy infrastructure and industrial operators."
            ),
            "sector_classification": "capex_intensive",
        }

    if sic in ("2834", "2836") and not gaap_profitable:
        if any(t in bmd for t in ("pre-revenue", "clinical stage", "pipeline", "phase")):
            return {
                "primary_metric":       "risk-adjusted NPV (rNPV) of pipeline",
                "secondary_metric":     "EV/Peak Sales of lead asset (comparable biotech transactions as reference)",
                "methodology_rationale": (
                    "Pre-revenue biotechnology company; risk-adjusted NPV (rNPV) of the "
                    "clinical pipeline is the institutional standard, probability-weighting "
                    "approval outcomes and discounting peak sales. EV/Peak Sales of the lead "
                    "asset provides a secondary cross-check anchored to comparable biotech "
                    "M&A and licensing transactions."
                ),
                "sector_classification": "biotech_pre_revenue",
            }

    # ── Step 4: Default profitability-based selection ─────────────────────────
    if gaap_profitable:
        base = {
            "primary_metric":       "EV/EBITDA",
            "secondary_metric":     "EV/EBIT",
            "methodology_rationale": (
                "GAAP-profitable company; EV/EBITDA is the primary metric for comparison "
                "across capital structure differences, with EV/EBIT as secondary to "
                "capture the D&A burden on capital-intensive businesses."
            ),
            "sector_classification": "standard_profitable",
        }
    else:
        base = {
            "primary_metric":       "EV/Revenue",
            "secondary_metric":     "Forward EV/EBITDA",
            "methodology_rationale": (
                "GAAP-loss company; EV/Revenue is the primary metric as EBITDA is "
                "negative or not meaningful. Forward EV/EBITDA is the secondary metric "
                "where a visible path to profitability within 24 months is indicated."
            ),
            "sector_classification": "standard_unprofitable",
        }

    # ── Step 5: Tech secondary metric appendage (additive) ────────────────────
    sic_int = int(sic) if sic.isdigit() else 0
    if 7370 <= sic_int <= 7389:
        saas_terms       = ("subscription", "saas", "streaming", "subscriber")
        social_terms     = ("social", "monthly active", "mau", "consumer app", "dau")
        marketplace_terms= ("marketplace", "gmv", "gross merchandise")
        if any(t in bmd for t in saas_terms):
            base["secondary_metric"] = base["secondary_metric"] + ", EV/Subscribers"
        elif any(t in bmd for t in social_terms):
            base["secondary_metric"] = base["secondary_metric"] + ", EV/MAU"
        elif any(t in bmd for t in marketplace_terms):
            base["secondary_metric"] = base["secondary_metric"] + ", EV/GMV"

    return base


def enrich_valuation_metric_selection(memo: dict) -> dict:
    """
    Extract inputs from memo and call select_valuation_metric().
    Injects primary_metric, secondary_metric, methodology_rationale,
    sector_classification, and sector_specific_metrics into valuation{}.

    Uses setdefault so Opus-populated values are preserved if already set.
    """
    fin = memo.get("financials") or {}
    sic = str(memo.get("sic_code") or "").strip()
    biz = (memo.get("business_overview") or {}).get("business_model") or ""

    net_income    = fin.get("net_income_usd_millions")
    gaap_profitable = net_income is not None and net_income >= 0

    # Count distinct segments — support both schema versions
    segments      = fin.get("segments") or fin.get("segment_breakdown") or []
    segment_count = len(segments)

    # Resolve TTM revenue for intensity calculations
    rev = fin.get("revenue_ttm_usd_millions")
    if rev is None:
        rev_obj = fin.get("revenue_usd_millions")
        if isinstance(rev_obj, dict):
            rev = rev_obj.get("ttm") or rev_obj.get("year_minus_1")
        elif isinstance(rev_obj, (int, float)):
            rev = rev_obj

    # Lease intensity
    rent  = fin.get("rent_expense_usd_millions")
    lease_intensity = (rent / rev * 100) if rent and rev else None

    # Capex intensity
    capex = fin.get("capex_usd_millions")
    capex_intensity = (capex / rev * 100) if capex and rev else None

    result = select_valuation_metric(
        sic, gaap_profitable, biz, segment_count,
        lease_intensity, capex_intensity
    )

    val = memo.setdefault("valuation", {})
    val.setdefault("primary_metric",        result["primary_metric"])
    val.setdefault("secondary_metric",      result["secondary_metric"])
    val.setdefault("methodology_rationale", result["methodology_rationale"])
    val.setdefault("sector_classification", result["sector_classification"])
    val.setdefault("sector_specific_metrics", {})

    log.info(
        f"Metric selection: primary={result['primary_metric']}, "
        f"secondary={result['secondary_metric']}, "
        f"class={result['sector_classification']}"
    )
    return memo



def apply_valuation_rules(memo: dict) -> dict:
    """
    1. Sector-aware RF-07 metric gating (all deals):
       RF-07A only fires when EV/Revenue is the primary or secondary metric.
       RF-07B only fires when EV/EBITDA is the primary or secondary metric.
       RF-07 (catch-all) fires regardless of metric.

    2. Suppress valuation flags for unpriced deals:
       When proposed_price_range is null/empty/TBD, RF-07/07A/07B are not
       applicable — no offering price has been set. Sets VA to neutral 6.0,
       removes any RF-07* flags, and sets pricing_tbd_flag=True.
    """
    # ── Sector-aware metric gating (runs for all deals) ──────────────────────
    val        = memo.get("valuation") or {}
    primary_m  = (val.get("primary_metric")   or "").upper()
    secondary_m= (val.get("secondary_metric") or "").upper()

    # Only gate if metric selection was run (primary_metric is non-empty)
    if primary_m:
        ev_rev_selected   = "EV/REVENUE"  in primary_m  or "EV/REVENUE"  in secondary_m
        ev_ebitda_selected= "EV/EBITDA"   in primary_m  or "EV/EBITDA"   in secondary_m

        rf_flags   = memo.get("red_flags") or []
        kept       = []
        rm_metric  = []
        for flag in rf_flags:
            fid = (flag.get("flag_id") or flag.get("code") or "").upper().replace("-", "")
            if fid == "RF07A" and not ev_rev_selected:
                rm_metric.append(fid)
            elif fid == "RF07B" and not ev_ebitda_selected:
                rm_metric.append(fid)
            else:
                kept.append(flag)
        if rm_metric:
            memo["red_flags"]      = kept
            memo["red_flag_count"] = len(kept)
            adj = list((memo.setdefault("scores", {})).get("adjustments") or [])
            adj.append({
                "rule":    "RF-07 sector metric gating",
                "detail":  (
                    f"Removed {', '.join(rm_metric)} — metric not applicable to "
                    f"selected methodology (primary: {primary_m})"
                ),
                "penalty": 0,
            })
            memo["scores"]["adjustments"] = adj
            log.info(f"RF-07 metric gating: removed {rm_metric} (primary={primary_m})")

    # ── Unpriced deal suppression ─────────────────────────────────────────────
    price_range = (memo.get("proposed_price_range") or "").strip().upper()
    unpriced_values = {"", "TBD", "N/A", "\u2014", "-", "PENDING", "TO BE DETERMINED"}
    if price_range and price_range not in unpriced_values:
        return memo  # priced deal — metric gating already applied above

    scores   = memo.get("scores") or {}
    old_va   = scores.get("valuation_attractiveness")

    # Remove any RF-07/07A/07B flags Opus may have triggered
    rf_flags    = memo.get("red_flags") or []
    kept_flags  = []
    removed_ids = []
    for flag in rf_flags:
        flag_id = (flag.get("flag_id") or flag.get("code") or "").upper().replace("-", "")
        if flag_id in ("RF07", "RF07A", "RF07B"):
            removed_ids.append(flag_id)
        else:
            kept_flags.append(flag)

    memo["red_flags"]     = kept_flags
    memo["red_flag_count"] = len(kept_flags)

    # Set VA to neutral 6.0
    scores["valuation_attractiveness"] = 6.0

    fhr_w = scores.get("fhr_weight_used") or 0.15
    va_w  = scores.get("va_weight_used")  or 0.20
    bmq = scores.get("business_model_quality") or 0
    fhr = scores.get("financial_health_runway") or 0
    mcp = scores.get("market_competitive_position") or 0
    mg  = scores.get("management_governance") or 0
    new_wt = round((bmq * 0.25 + fhr * fhr_w + mcp * 0.20 + mg * 0.20 + 6.0 * va_w) * 10, 1)

    adj_list = list(scores.get("adjustments") or [])
    detail = "No offering price disclosed — valuation flags suppressed; VA set to 6.0 (neutral)"
    if removed_ids:
        detail += f" (removed: {', '.join(removed_ids)})"
    adj_list.append({
        "rule":    "Valuation deferred (unpriced deal)",
        "detail":  detail,
        "penalty": 0,
    })
    scores["weighted_total"] = new_wt
    scores["adjustments"]    = adj_list
    memo["scores"]           = scores
    memo["pricing_tbd_flag"] = True
    log.info(f"Pricing TBD — valuation flags suppressed, VA set to 6.0, new score: {new_wt}")
    return memo


def apply_governance_cap(memo: dict) -> dict:
    """
    Apply founder track record deduction for dual-class governance structures.

    Replaces the old 5.0 hard cap with a nuanced deduction based on four tiers:
      proven_operator       → −1.0 pt from M&G
      emerging_operator     → −2.5 pts from M&G
      first_time_public_ceo → −4.0 pts from M&G
      concerning_history    → −5.0 pts from M&G

    Additional −1.5 pts if founder voting control >80% post-IPO AND tier is
    first_time_public_ceo or concerning_history.
    """
    ownership  = memo.get("ownership") or {}
    management = memo.get("management") or {}
    scores     = memo.get("scores") or {}
    mg_score   = scores.get("management_governance")

    if mg_score is None:
        return memo

    dual_class = ownership.get("dual_class_structure") or False
    if not dual_class:
        return memo

    TIER_DEDUCTIONS = {
        "proven_operator":       1.0,
        "emerging_operator":     2.5,
        "first_time_public_ceo": 4.0,
        "concerning_history":    5.0,
    }

    tier = (management.get("founder_track_record_assessment") or "").strip().lower()
    if tier not in TIER_DEDUCTIONS:
        # Opus did not populate — default to emerging_operator for dual-class deals
        tier = "emerging_operator"
        management["founder_track_record_assessment"] = tier
        memo["management"] = management

    deduction = TIER_DEDUCTIONS[tier]

    # Additional penalty for extreme voting concentration + weak track record
    founder_voting = ownership.get("founder_post_ipo_voting_control_pct") or 0
    extra_penalty  = 0.0
    if founder_voting > 80 and tier in ("first_time_public_ceo", "concerning_history"):
        extra_penalty = 1.5

    total_deduction = deduction + extra_penalty
    old_mg  = mg_score
    new_mg  = max(0.0, round(mg_score - total_deduction, 1))
    scores["management_governance"] = new_mg

    fhr_w = scores.get("fhr_weight_used") or 0.15
    va_w  = scores.get("va_weight_used")  or 0.20
    bmq = scores.get("business_model_quality") or 0
    fhr = scores.get("financial_health_runway") or 0
    mcp = scores.get("market_competitive_position") or 0
    va  = scores.get("valuation_attractiveness") or 0
    new_wt = round((bmq * 0.25 + fhr * fhr_w + mcp * 0.20 + new_mg * 0.20 + va * va_w) * 10, 1)

    adj_list = list(scores.get("adjustments") or [])
    detail = f"Dual-class governance — {tier} (−{deduction:.1f}pt deduction)"
    if extra_penalty > 0:
        detail += f" + −{extra_penalty:.1f}pt for >{founder_voting:.0f}% voting concentration"
    adj_list.append({
        "rule":    "Dual-class governance assessment",
        "detail":  detail,
        "penalty": round(-(total_deduction * 0.20 * 10), 1),
    })
    scores["weighted_total"] = new_wt
    scores["adjustments"]    = adj_list
    memo["scores"]           = scores
    log.info(f"Governance deduction applied — M&G {old_mg}→{new_mg} ({tier}), new score: {new_wt}")
    return memo



def apply_rf23_lockup(memo: dict) -> dict:
    """
    Post-hoc RF-23 enforcement from lockup_analysis structured fields.
    Evaluates objective trigger conditions and applies deductions to M&G.
    Python owns these deductions — Opus sets rf23_triggered/rf23_reason only.

    Trigger hierarchy (worst condition wins; no stacking):
      CRITICAL -3.0: secondary_pct >20% AND lockup_days <180
      CRITICAL -3.0: no lockup disclosed for any insider class
      HIGH     -2.5: lockup_days <90
      HIGH     -2.5: Opus-flagged rf23_triggered (performance trigger or carveouts)
    Standard lockups (>=90 days, clean cliff/rolling) → no deduction.
    """
    la = (memo.get("lockup_analysis") or {})
    if not la:
        return memo
    scores = memo.get("scores") or {}
    mg = scores.get("management_governance")
    if mg is None:
        return memo

    adjustments = list(scores.get("adjustments") or [])
    red_flags    = list(memo.get("red_flags") or [])

    lockup_days = la.get("lockup_days")
    sec_pct     = la.get("secondary_shares_pct_offering")
    sec_mm      = la.get("secondary_shares_millions")

    deduction    = 0.0
    is_critical  = False
    fired_reason = []

    # CRITICAL: secondary >20% AND lockup <180 days (combined condition)
    if sec_pct is not None and sec_pct > 20 and lockup_days is not None and lockup_days < 180:
        fired_reason.append(
            f"Secondary shares {sec_pct:.1f}% of offering combined with "
            f"lockup of only {lockup_days} days — insiders cashing out with "
            f"abbreviated lockup signals coordinated exit and lack of conviction."
        )
        deduction   = max(deduction, 3.0)
        is_critical = True

    # CRITICAL: no lockup disclosed for any insider class (with secondary shares)
    if lockup_days is None and sec_mm is not None and sec_mm > 0:
        fired_reason.append(
            f"No lockup period disclosed for any insider class while "
            f"{sec_mm}M secondary shares are present in the offering."
        )
        deduction   = max(deduction, 3.0)
        is_critical = True

    # HIGH: lockup <90 days
    if lockup_days is not None and lockup_days < 90:
        fired_reason.append(
            f"Lockup period of {lockup_days} days is below the 90-day "
            f"institutional minimum — signals insiders positioning for rapid post-IPO exit."
        )
        deduction = max(deduction, 2.5)

    # HIGH: Opus flagged rf23_triggered (performance trigger or material carveouts)
    if la.get("rf23_triggered") and la.get("rf23_reason") and not fired_reason:
        fired_reason.append(la.get("rf23_reason", "Lockup condition flagged by analysis."))
        deduction = max(deduction, 2.5)

    if not fired_reason or deduction == 0.0:
        return memo

    severity = "CRITICAL" if is_critical else "HIGH"
    reason   = " | ".join(fired_reason)

    # Update lockup_analysis flags
    la["rf23_triggered"] = True
    la["rf23_reason"]    = reason
    memo["lockup_analysis"] = la

    # Apply deduction to M&G and recalculate weighted_total
    new_mg = round(max(0, mg - deduction), 1)
    scores["management_governance"] = new_mg

    # Use stored weights; default to base weights if not leveraged issuer
    if memo.get("leveraged_issuer_flag"):
        wt = round(
            scores.get("business_model_quality",    0) * 0.25 +
            scores.get("financial_health_runway",    0) * 0.20 +
            scores.get("market_competitive_position",0) * 0.20 +
            new_mg                                       * 0.20 +
            scores.get("valuation_attractiveness",  0) * 0.15,
            1
        )
    else:
        wt = round(
            scores.get("business_model_quality",    0) * 0.25 +
            scores.get("financial_health_runway",    0) * 0.15 +
            scores.get("market_competitive_position",0) * 0.20 +
            new_mg                                       * 0.20 +
            scores.get("valuation_attractiveness",  0) * 0.20,
            1
        )
    scores["weighted_total"] = wt

    adjustments.append(
        f"RF-23 {severity}: {reason} "
        f"\u2212{deduction} pts from M&G ({mg} \u2192 {new_mg})."
    )
    scores["adjustments"] = adjustments
    memo["scores"]        = scores

    # Add to red_flags[] if not already present
    existing = [f.get("code","") if isinstance(f, dict) else "" for f in red_flags]
    if "RF-23" not in existing:
        red_flags.append({
            "code":        "RF-23",
            "name":        "INSIDER LIQUIDITY OVERHANG",
            "severity":    severity,
            "triggered":   True,
            "source":      "python_post_hoc",
            "description": reason,
        })
        memo["red_flags"]      = red_flags
        memo["red_flag_count"] = memo.get("red_flag_count", 0) + 1

    return memo

def apply_scoring_adjustments(memo: dict) -> dict:
    """
    Apply post-hoc score penalties and structural overrides after Opus scoring.

    Steps (in order):
      0. enrich_valuation_metric_selection — select primary/secondary metric (runs before this fn)
      1. apply_valuation_rules       — sector-aware RF-07 gating + suppress all for unpriced deals
      2. apply_leverage_adjustments  — reweight FHR/VA for leveraged issuers
      3. apply_leverage_floor        — detect high leverage, note in adjustments (no cap)
      4. apply_governance_cap        — founder track record deduction for dual-class
      5. apply_rf23_lockup           — lockup condition deductions (graduated RF-23 framework)
      6. RF-20 syndicate spread      — -1.5 per excess underwriter, capped at -5
      6. Re-derive recommendation    — 75/65/55 thresholds
      7. RF-01B going concern        — AUTOMATIC PASS override (structural)

    After all adjustments, re-derives recommendation from weighted_total.
    """
    memo = apply_valuation_rules(memo)
    memo = apply_leverage_adjustments(memo)
    memo = apply_leverage_floor(memo)
    memo = apply_governance_cap(memo)
    memo = apply_rf23_lockup(memo)

    scores = memo.get("scores") or {}
    wt = scores.get("weighted_total")
    if wt is None:
        return memo

    adjustments = list(scores.get("adjustments") or [])
    underwriters = memo.get("lead_underwriters") or []
    offering_mm  = memo.get("offering_size_usd_millions") or 0

    if len(underwriters) > 4 and 0 < offering_mm < 500:
        excess  = len(underwriters) - 4
        penalty = round(min(5.0, excess * 1.5), 1)
        adjustments.append({
            "rule":    "RF-20 Syndicate spread",
            "detail":  f"{len(underwriters)} underwriters on ${offering_mm}M deal",
            "penalty": -penalty,
        })
        wt = round(wt - penalty, 1)
        scores["weighted_total"] = wt
        scores["adjustments"]    = adjustments
        memo["scores"]           = scores

    # Re-derive recommendation from final weighted_total (unless going_concern overrides)
    if not memo.get("going_concern"):
        memo["recommendation"] = _derive_recommendation(wt)

    # RF-01B structural going concern: AUTOMATIC PASS. Enforced independently.
    gc_type = memo.get("going_concern_type") or ""
    if memo.get("going_concern") and gc_type != "capital_deficient":
        if memo.get("recommendation") != "PASS":
            log.warning(
                f"going_concern=true (type={gc_type}) but recommendation was "
                f"{memo.get('recommendation')} — forcing PASS per RF-01B"
            )
        memo["recommendation"] = "PASS"

    return memo


def _error_stub(
    company: str,
    filing_date: str,
    form_type: str,
    error_msg: str,
    raw_response,
) -> dict:
    """Build a stub memo for manual review when analysis fails."""
    return {
        "company_name":    company,
        "filing_date":     filing_date,
        "form_type":       form_type,
        "recommendation":  "ERROR",
        "executive_summary": f"Analysis failed -- {error_msg}",
        "scores":          {"weighted_total": None},
        "red_flags":       [],
        "red_flag_count":  0,
        "going_concern":   False,
        "is_amendment":    form_type == "S-1/A",
        "prior_memo_date": None,
        "amendment_changes_summary": None,
        "_raw_claude_response": raw_response,  # preserved for manual review
        "run_timestamp":   datetime.now(PACIFIC).isoformat(),
    }


# ─────────────────────────────────────────────
# SAVE & ORGANIZE
# ─────────────────────────────────────────────

def save_memo(memo: dict, run_date: str) -> None:
    """
    Write a memo JSON file to the dated directory.

    For S-1/A amendments where a prior memo exists (prior_memo_date is set),
    the updated memo is ALSO written back to the prior date's directory so
    that the canonical slug-based lookup always returns the latest analysis.
    The prior file is backed up as {slug}_prior_{prior_date}.json before overwrite.
    """
    date_dir = DATA_DIR / run_date
    date_dir.mkdir(parents=True, exist_ok=True)

    company_slug = _company_slug(memo.get("company_name", "unknown"))
    filename = date_dir / f"{company_slug}.json"

    with open(filename, "w") as f:
        json.dump(memo, f, indent=2)
    log.info(f"Saved memo: {filename}")

    # Amendment update: overwrite prior memo so slug lookup returns latest analysis
    prior_date = memo.get("prior_memo_date")
    if memo.get("is_amendment") and prior_date:
        prior_dir = DATA_DIR / prior_date
        prior_path = prior_dir / f"{company_slug}.json"
        if prior_path.exists():
            # Back up the original before overwriting
            backup_path = prior_dir / f"{company_slug}_prior_{prior_date}.json"
            if not backup_path.exists():
                backup_path.write_text(prior_path.read_text(encoding="utf-8"), encoding="utf-8")
                log.info(f"Backed up prior memo: {backup_path.name}")
            with open(prior_path, "w") as f:
                json.dump(memo, f, indent=2)
            log.info(f"Updated prior memo in-place: {prior_path}")


def update_manifest(run_date: str) -> None:
    """Maintain a top-level _manifest.json so the desktop app can discover all sessions."""
    manifest_path = DATA_DIR / "_manifest.json"
    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest = json.load(f)
    else:
        manifest = {"dates": []}
    if run_date not in manifest["dates"]:
        manifest["dates"].append(run_date)
        manifest["dates"].sort(reverse=True)
    manifest["last_updated"] = datetime.now(PACIFIC).isoformat()
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)


def save_daily_index(memos: list, run_date: str) -> dict:
    """Save a summary index file for the day -- used by the desktop app."""
    date_dir = DATA_DIR / run_date
    date_dir.mkdir(parents=True, exist_ok=True)
    index = {
        "run_date":          run_date,
        "run_timestamp":     datetime.now(PACIFIC).isoformat(),
        "total_filings":     len(memos),
        "underwrite_count":  sum(1 for m in memos if m.get("recommendation") == "UNDERWRITE"),
        "conditional_count": sum(1 for m in memos if m.get("recommendation","").startswith("CONDITIONAL")),
        "pass_count":        sum(1 for m in memos if m.get("recommendation") == "PASS"),
        "error_count":       sum(1 for m in memos if m.get("recommendation") == "ERROR"),
        "companies": [
            {
                "company_name":               m.get("company_name"),
                "proposed_ticker":            m.get("proposed_ticker"),
                "sector":                     m.get("sector"),
                "offering_size_usd_millions": m.get("offering_size_usd_millions"),
                "recommendation":             m.get("recommendation"),
                "score":    (m.get("scores") or {}).get("weighted_total"),
                "red_flag_count":             m.get("red_flag_count", 0),
                "going_concern":              m.get("going_concern", False),
                "is_amendment":               m.get("is_amendment", False),
                "file": f"{_company_slug(m.get('company_name', 'unknown'))}.json",
            }
            for m in sorted(
                memos,
                key=lambda x: (x.get("scores") or {}).get("weighted_total") or 0,
                reverse=True,
            )
        ],
    }
    with open(date_dir / "_index.json", "w") as f:
        json.dump(index, f, indent=2)
    log.info(f"Saved daily index for {run_date}")
    return index


def validate_memo_index(run_date: str) -> None:
    """
    Post-save index validator — runs after every memo save.

    1. Reads _index.json for run_date and checks it against the app-expected
       schema: run_date (str), run_timestamp (str), companies[] list where each
       entry has company_name, proposed_ticker, recommendation, score, file, and
       filing_date.
    2. If any field is missing or mis-typed, rebuilds every entry from the saved
       memo JSON files on disk and rewrites _index.json.
    3. Ensures _manifest.json includes run_date; adds it if absent.
    4. Prints a single confirmation line so the result is always visible in
       terminal output.
    """
    date_dir    = DATA_DIR / run_date
    index_path  = date_dir / "_index.json"
    manifest_path = DATA_DIR / "_manifest.json"
    rebuilt = False

    # ── 1. Load existing index ────────────────────────────────────────────
    index = None
    if index_path.exists():
        try:
            with open(index_path, encoding="utf-8") as f:
                index = json.load(f)
        except (json.JSONDecodeError, OSError):
            index = None

    # ── 2. Validate top-level structure ──────────────────────────────────
    schema_ok = (
        index is not None
        and isinstance(index.get("run_date"), str)
        and isinstance(index.get("run_timestamp"), str)
        and isinstance(index.get("companies"), list)
    )

    # Accept legacy "memos" key in place of "companies"
    if index is not None and not schema_ok:
        if "memos" in index and "companies" not in index:
            index["companies"] = index.pop("memos")
            schema_ok = (
                isinstance(index.get("run_date"), str)
                and isinstance(index.get("run_timestamp"), str)
                and isinstance(index.get("companies"), list)
            )

    # ── 3. Full rebuild if top-level is broken ────────────────────────────
    if not schema_ok:
        memo_files = sorted(
            [f for f in date_dir.glob("*.json") if f.name != "_index.json"]
        ) if date_dir.exists() else []
        companies = []
        for mf in memo_files:
            try:
                with open(mf, encoding="utf-8") as f:
                    m = json.load(f)
                companies.append({
                    "company_name":               m.get("company_name", ""),
                    "proposed_ticker":            m.get("proposed_ticker", ""),
                    "sector":                     m.get("sector", ""),
                    "offering_size_usd_millions": (m.get("offering") or {}).get("offering_size_usd_millions"),
                    "recommendation":             m.get("recommendation", ""),
                    "score":   (m.get("scores") or {}).get("weighted_total"),
                    "red_flag_count":             m.get("red_flag_count", 0),
                    "going_concern":              m.get("going_concern", False),
                    "is_amendment":               m.get("is_amendment", False),
                    "filing_date":                m.get("filing_date", ""),
                    "file":                       mf.name,
                })
            except Exception:
                pass
        index = {
            "run_date":          run_date,
            "run_timestamp":     datetime.now(PACIFIC).isoformat(),
            "total_filings":     len(companies),
            "underwrite_count":  sum(1 for c in companies if c.get("recommendation") == "UNDERWRITE"),
            "conditional_count": sum(1 for c in companies if (c.get("recommendation") or "").startswith("CONDITIONAL")),
            "pass_count":        sum(1 for c in companies if c.get("recommendation") == "PASS"),
            "error_count":       sum(1 for c in companies if c.get("recommendation") == "ERROR"),
            "companies": sorted(companies, key=lambda x: x.get("score") or 0, reverse=True),
        }
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)
        rebuilt = True

    else:
        # ── 4. Validate and patch individual company entries ──────────────
        REQUIRED_ENTRY_FIELDS = ("company_name", "recommendation", "file")
        entry_patched = False
        for entry in index["companies"]:
            # Normalize field aliases
            if "ticker" in entry and "proposed_ticker" not in entry:
                entry["proposed_ticker"] = entry.pop("ticker")
            if "filename" in entry and "file" not in entry:
                entry["file"] = entry.pop("filename")

            # Check whether any required field is missing
            missing = [f for f in REQUIRED_ENTRY_FIELDS if not entry.get(f)]
            needs_score    = entry.get("score") is None
            needs_filing_date = not entry.get("filing_date")

            if missing or needs_score or needs_filing_date:
                memo_file = date_dir / (entry.get("file") or "")
                if memo_file.exists():
                    try:
                        with open(memo_file, encoding="utf-8") as f:
                            m = json.load(f)
                        for field in REQUIRED_ENTRY_FIELDS:
                            if not entry.get(field):
                                entry[field] = m.get(field) or m.get(
                                    "proposed_ticker" if field == "ticker" else field, "")
                        if not entry.get("proposed_ticker"):
                            entry["proposed_ticker"] = m.get("proposed_ticker", "")
                        if needs_score:
                            entry["score"] = (m.get("scores") or {}).get("weighted_total")
                        if needs_filing_date:
                            entry["filing_date"] = m.get("filing_date", "")
                        entry_patched = True
                    except Exception:
                        pass

        if entry_patched:
            with open(index_path, "w", encoding="utf-8") as f:
                json.dump(index, f, indent=2)
            rebuilt = True

    # ── 5. Ensure manifest includes run_date ──────────────────────────────
    manifest_has_date = False
    if manifest_path.exists():
        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
            manifest_has_date = run_date in manifest.get("dates", [])
        except Exception:
            pass
    if not manifest_has_date:
        update_manifest(run_date)
        rebuilt = True

    # ── 6. Confirmation ───────────────────────────────────────────────────
    if rebuilt:
        print(f"  INDEX REBUILT — structural mismatch corrected [{run_date}]")
    else:
        print(f"  INDEX VALIDATED — memo will appear in dashboard [{run_date}]")


# ─────────────────────────────────────────────
# PDF QUALITY VALIDATION
# ─────────────────────────────────────────────

def validate_pdf_output(memo: dict) -> list:
    """
    Validate a memo dict for issues that would cause PDF rendering problems.
    Checks run against the JSON structure; issues map to the section numbers
    shown in the rendered PDF.

    Returns a list of issue strings, each prefixed with its section number.
    """
    issues = []

    # ── helpers ────────────────────────────────────────────────────────────
    _EMPTY_STRINGS = {"", "—", "-", "not available", "not available.",
                      "no data available", "n/a", "null", "none", "tbd"}

    def is_empty(val):
        if val is None:
            return True
        if isinstance(val, str):
            return val.strip().lower() in _EMPTY_STRINGS
        if isinstance(val, (list, dict)):
            return len(val) == 0
        return False

    def _scan_object_object(val, path):
        """Recursively find any string that looks like a leaked JS object."""
        found = []
        if isinstance(val, str):
            stripped = val.strip().lower()
            if "[object object]" in stripped or stripped.startswith("[object"):
                found.append(f"{path}: \"{val[:80]}\"")
        elif isinstance(val, dict):
            for k, v in val.items():
                found.extend(_scan_object_object(v, f"{path}.{k}"))
        elif isinstance(val, list):
            for i, v in enumerate(val):
                found.extend(_scan_object_object(v, f"{path}[{i}]"))
        return found

    def _field_is_narrative_but_dict(field_name, val):
        """Flag narrative fields that are dicts instead of strings (schema mismatch)."""
        narrative_fields = {
            "executive_summary", "deal_committee_recommendation",
            "deal_committee_narrative", "business_overview",
            "key_risk_narrative", "macro_sector_context",
            "proceeds_narrative", "accounting_quality_summary",
        }
        return field_name in narrative_fields and isinstance(val, dict)

    # ── Check 1: Sections with no renderable content ───────────────────────
    section_checks = [
        ("Cover", "Executive Summary",          memo.get("executive_summary")),
        ("01",    "Deal Committee Rec.",         memo.get("deal_committee_recommendation")
                                                 or memo.get("deal_committee_narrative")),
        ("02",    "Business Overview",           memo.get("business_overview")),
        ("04",    "Risk & Red Flags",            memo.get("red_flags")),
        ("05",    "Litigation",                  (memo.get("litigation_regulatory") or {})
                                                 .get("litigation_risk_level")
                                                 or (memo.get("litigation_regulatory") or {})
                                                 .get("litigation_summary")),
        ("06",    "Financial Snapshot",          memo.get("financials")),
        ("07",    "Use of Proceeds",             memo.get("use_of_proceeds")),
        ("08",    "Valuation Analysis",          memo.get("valuation")),
        ("09",    "Revenue Quality",             memo.get("revenue_quality")),
        ("12",    "Macro & Sector Context",      memo.get("macro_sector_context")),
        ("13",    "Underwriting Syndicate",      memo.get("lead_underwriters")),
        ("18",    "Accounting Practices",        memo.get("accounting_practices")),
    ]
    for sec, label, val in section_checks:
        if is_empty(val):
            issues.append(f"Section {sec} ({label}): no content — will render empty or 'Not available'")

    # ── Check 2: [object Object] anywhere in memo ──────────────────────────
    for hit in _scan_object_object(memo, "memo"):
        issues.append(f"[object Object] at {hit}")

    # Also flag narrative fields that are dicts instead of strings
    for k, v in memo.items():
        if _field_is_narrative_but_dict(k, v):
            issues.append(f"Field '{k}' is a dict but should be a string — will render as [object Object]")

    # ── Check 3: Critical fields null or empty ─────────────────────────────
    fin = memo.get("financials") or {}
    rev = fin.get("revenue_usd_millions") or {}
    if rev.get("ttm") is None and rev.get("year_minus_1") is None:
        issues.append("Section 06 (Financial Snapshot): all revenue fields null — table will be blank")
    if fin.get("gross_margin_pct") is None:
        issues.append("Section 06 (Financial Snapshot): gross_margin_pct null")
    if is_empty(memo.get("recommendation")):
        issues.append("CRITICAL: recommendation field empty — cover badge will be blank")
    if is_empty(memo.get("deal_committee_recommendation")
                or memo.get("deal_committee_narrative")):
        issues.append("Section 01 (Deal Committee Rec.): narrative empty — section will show 'Not available'")

    # ── Check 4: Part divider targets must have content ────────────────────
    # Part dividers are injected immediately before these sections; if the
    # section has no content the PDF shows a part label with nothing below it.
    part_targets = [
        ("04", "Part II  (Risk Assessment)",            memo.get("red_flags")),
        ("06", "Part III (Business & Financial)",       memo.get("financials")),
        ("13", "Part IV  (Deal Structure & Diligence)", memo.get("lead_underwriters")),
    ]
    for sec, part_label, val in part_targets:
        if is_empty(val):
            issues.append(
                f"Section {sec} triggers {part_label} divider but has no content — "
                f"likely blank page in PDF"
            )

    return issues


def _print_pdf_quality_report(company: str, issues: list) -> None:
    """Print the PDF quality check summary and log all issues."""
    count = len(issues)
    bar = "-" * 55
    print(f"\n  {bar}")
    print(f"  PDF QUALITY CHECK: {count} issue{'s' if count != 1 else ''} found  [{company}]")
    if issues:
        for issue in issues:
            print(f"    ⚠  {issue}")
            log.warning(f"PDF quality [{company}]: {issue}")
    else:
        print(f"    ✓  No rendering issues detected.")
    if count > 3:
        print(f"\n  !! WARNING — memo has significant rendering gaps, review before sending to MD.")
        log.warning(f"[{company}] SIGNIFICANT PDF QUALITY WARNING: {count} issues found.")
    print(f"  {bar}")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main() -> None:
    if not ANTHROPIC_API_KEY:
        raise EnvironmentError("ANTHROPIC_API_KEY environment variable not set.")

    run_date = datetime.now(PACIFIC).strftime("%Y-%m-%d")
    log.info(f"IPO Screener starting -- {run_date}")
    print(f"\n{'='*55}")
    print(f"  IPO S-1 DAILY SCREENER  |  {run_date}  |  7:00 AM PT")
    print(f"{'='*55}\n")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    filings = fetch_new_s1_filings()

    if not filings:
        msg = f"No new S-1 filings found in the past {LOOKBACK_DAYS} days. Standing by."
        log.info(msg)
        print(f"  {msg}\n")
        save_daily_index([], run_date)
        update_manifest(run_date)
        validate_memo_index(run_date)
        return

    total = len(filings)
    print(f"  Found {total} new S-1 filing(s). Running analysis...\n")
    if total > PRIORITY_FILINGS:
        print(f"  Top {PRIORITY_FILINGS} flagged as priority. Remaining queued.\n")

    memos = []
    for i, filing in enumerate(filings):
        amend_tag = " [AMENDMENT]" if filing.get("form_type") == "S-1/A" else ""
        print(f"  [{i+1}/{total}] {filing['company']} ({filing['form_type']}){amend_tag}...")
        memo = analyze_filing(client, filing)
        memos.append(memo)
        save_memo(memo, run_date)
        issues = validate_pdf_output(memo)
        _print_pdf_quality_report(memo.get("company_name", filing["company"]), issues)
        time.sleep(2)  # rate limiting between filings

    index = save_daily_index(memos, run_date)
    update_manifest(run_date)
    validate_memo_index(run_date)

    print(f"\n{'-'*55}")
    print(f"  SCREENING COMPLETE  |  {total} filings analyzed")
    print(f"  UNDERWRITE: {index['underwrite_count']}  |  CONDITIONAL: {index['conditional_count']}  |  PASS: {index['pass_count']}  |  ERROR: {index['error_count']}")
    print(f"{'-'*55}")
    print(f"\n  TOP RECOMMENDATIONS (by score):")
    for c in index["companies"][:PRIORITY_FILINGS]:
        score   = f"{c['score']:.0f}/100" if c["score"] else "N/A"
        flags   = f"  {c['red_flag_count']} flags" if c["red_flag_count"] else ""
        gc      = "  GOING CONCERN" if c["going_concern"] else ""
        amended = "  [AMD]" if c.get("is_amendment") else ""
        print(f"  * {c['company_name']:35} {c['recommendation']:12} {score}{flags}{gc}{amended}")
    print(f"\n  Memos saved to: {DATA_DIR / run_date}")
    print(f"{'='*55}\n")
    log.info("Screening run complete.")


if __name__ == "__main__":
    main()
