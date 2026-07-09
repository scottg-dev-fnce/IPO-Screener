---
name: syndicate-risk-rf20
type: pattern
version: 1
last_written: 2026-07-08
source_analysis: csquare_inc_amendments_1_2_original
confidence: medium
observations: 1
expires: never
---

# RF-20 Syndicate Risk & Underwriter Conflict Patterns

## Syndicate Size as a Signal

| Underwriter Count | Signal |
|---|---|
| 2-4 | Clean deal; tight, confident book |
| 5-7 | Normal for large ($500M+) or complex deals |
| 8-10 | Elevated; possible distribution concern OR complex conflict management |
| 11-13 | Very high; sponsor relationship-driven (Canadian banks) OR book building difficulty |
| 14+ | Extreme; almost always signals distribution difficulty |

**RF-20 trigger:** >4 underwriters on a deal below $500M. On large deals, evaluate qualitatively — a 13-bank syndicate on a $1.25B deal is unusual but explainable by Canadian bank cluster (see Brookfield pattern).

## FINRA Rule 5121 Conflict Clusters

FINRA 5121 fires when an underwriter or its affiliate owns >10% of the issuer's equity. Triggers:
- Cannot confirm sales to discretionary accounts without written approval
- A Qualified Independent Underwriter (QIU) must be designated (typically the most arms-length underwriter in the syndicate)
- QIU is almost always RBC Capital Markets in Brookfield deals (independently held, not a revolver lender)

**Three types of underwriter conflict to track:**

1. **Equity conflict:** Underwriter affiliate owns >10% of issuer (Brookfield Securities LLC pattern)
2. **Debt repayment conflict:** Underwriter affiliate holds debt being repaid from IPO proceeds (TD/BMO/Scotia as VFN holders; Wells Fargo as revolver admin agent)
3. **Recent M&A conflict:** Underwriter was M&A advisor on an acquisition being described in the S-1

**Maximum conflict density observed:** Csquare Amendment No. 2 — 6 of 13 underwriters had FINRA 5121 conflicts simultaneously. This is the highest in our coverage.

## Representative vs. Book-Runner Distinction

- **Representatives:** listed first on cover page; lead the pricing and allocation decisions; hold lockup waiver authority. Most powerful position.
- **Book-runners:** allocated economics from the selling group; participate in roadshow but less control over deal execution
- **Co-managers:** smallest economics; typically relationship/distribution roles

For conflict analysis: focus on Representatives first (they control the deal), then book-runners with debt repayment conflicts (they have the most direct economic incentive to price deal favorably to get repaid).

## The "Dual Conflict" Test

A bank is maximally conflicted when it is BOTH:
- A lender whose debt is being repaid from IPO proceeds, AND
- An underwriter receiving fees from the IPO

In this scenario, the bank profits from: (a) debt repayment at par, (b) underwriting fee, AND (c) is incentivized to get the deal done at any price. Flag these banks explicitly in syndicate_assessment.

**Csquare triple-conflict banks:** TD Securities, BMO Capital Markets, Scotia Capital (revolver lenders + VFN holders + underwriters).

## QIU Selection Logic

The QIU is selected to be the **most independent** underwriter in the group. Rules of thumb:
- Must not hold any debt being repaid from proceeds
- Must not have its affiliate in the ownership chain
- Typically the most recent addition to the syndicate (often added specifically to serve as QIU)
- In Brookfield deals: RBC Capital Markets. In KKR deals: likely a different bank.

## Post-Hoc RF-20 Application

RF-20 is Python-applied after analysis returns. When writing memos manually:
- Record `total_underwriters` in `underwriting_syndicate`
- Set `rf20_triggered: true/false`
- Calculate: (total - 4) × 1.5, cap at 5.0
- Display score = weighted_total - rf20_penalty
- The cap of -5.0 means a 100-bank syndicate has the same penalty as a 7-bank syndicate
