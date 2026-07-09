---
name: colocation-data-center
type: sector
version: 1
last_written: 2026-07-08
source_analysis: csquare_inc_amendments_1_2_original
confidence: high
observations: 1
expires: never
---

# Carrier-Neutral Colocation & Interconnection Data Centers

SIC 7370 (Computer Programming, Data Processing). Primary public comps: EQIX, DLR.

## Business Model

Carrier-neutral colocation = licensed cabinet space + power + cooling in a shared facility. "Carrier-neutral" means the operator is agnostic to which networks/clouds run in the building — the value is the density of choices at the same physical location (network effect).

- **Revenue mix (enterprise colo):** Colocation ~75%, Interconnection ~10-12%, Metered power ~5-6%, Non-recurring ~4-5%
- **Interconnection** is the highest-margin segment but often declining as share of total revenue as platforms scale — watch for this trend
- **Recurring revenue:** ~90% of total (standard for mature colo operator)
- **Contract terms:** 1-7 year contracts; 33-month average remaining is healthy; <24 months is a warning sign

## Key Operating Metrics to Pull From Every Filing

| Metric | Healthy Range | Warning |
|---|---|---|
| Net Revenue Churn (quarterly) | <1.5% | >2.0% |
| Net Revenue Churn (annual) | <6% | >8% |
| Contracted power / sellable power | >90% utilization | <80% |
| Average remaining contract term | >30 months | <24 months |
| Bookings (YoY growth) | >20% | <10% |
| AI/HPC MRR as % of total | Growing; 15%+ is strong tailwind | Flat or declining |

**Annual churn of 7.9% (Csquare FY2025):** This is structurally elevated for the sector. Enterprise colocation should trend toward 4-6% annual churn at maturity. Above 8% signals competitive displacement or contract re-pricing pressure.

## Debt Structure: ABS vs. Corporate

Two distinct debt structures in the colo sector:

1. **REIT / Investment-Grade Corporate (EQIX, DLR):** Unsecured notes, revolving credit, low leverage (~5.5-6x). Rated BBB- or better. Access to public bond markets.
2. **PE-backed / ABS (Csquare, Cyxtera-era structures):** Bankruptcy-remote SPE issuer entities, ABS series with ARDs 5-7 years out, higher leverage (10-13x pre-IPO). No investment-grade rating. Revolver is the floating-rate component.

**Rule:** ABS-financed colo operators at IPO will always have: (a) Leveraged Issuer flag, (b) RF-14, (c) RF-19 if proceeds go to ABS/revolver paydown, (d) SPE entity disclosures in risk factors.

## Valuation Framework

- **Primary metric:** EV/Adj.EBITDA (GAAP D&A is too large to use GAAP EBITDA; FY2025 D&A typically 25-30% of revenue)
- **Sector range:** 18-30x depending on leverage. EQIX/DLR at 28-30x. Leveraged operators discount 30-40% to peers.
- **At 10x+ leverage:** expect 15-20x EV/Adj.EBITDA
- **Secondary metric:** EV/Revenue (typical 5-14x for colo; leveraged = 5-8x, investment-grade = 12-14x)
- **Finance leases:** always included in debt carrying value (~10-15% of total); whether to exclude from leverage denominator is a committee judgment call — be explicit about which basis is used

## Brownfield vs. Greenfield

- **Brownfield expansion** (existing buildings, add power/cooling): $4-8M/MW — correct capital intensity
- **Greenfield** (new builds): $8-15M/MW — much higher; not the primary model for enterprise colo
- Always verify: is capex guide for brownfield or greenfield? PE-backed platforms almost always brownfield.

## Accounting Considerations

- **Revenue recognition:** dual-framework (ASC 606 for service component + ASC 842 for lease component). Company uses "lessor practical expedient" to combine components when timing/pattern match. Standard for the sector.
- **Finance leases:** capital-lease treatment for equipment-intensive sites; ground leases may be finance or operating. Heavy finance lease ROU assets (~$500M-$600M range for a $1B-revenue operator) are normal, not aggressive.
- **D&A load:** 25-30% of revenue is typical; this is why GAAP net loss persists even with strong Adj.EBITDA. Don't penalize the GAAP income statement without checking D&A composition.
- **Goodwill:** acquisition-heavy PE platforms carry $400-700M goodwill; test annually; watch for impairment risk if churn accelerates.

## Competitive Moat Assessment

Genuine moats in colo:
1. **Physical real estate** — urban data centers cannot be replicated; zoning, power permits, fiber connectivity take 5-10 years
2. **Carrier/cloud density** — each additional provider increases switching cost for all existing tenants (network effect)
3. **Customer entanglement** — multi-year contracts, power infrastructure, cross-connects all create friction

Weak moats:
- Sub-scale platforms (<20 sites) have limited network effect
- Markets with new hyperscaler campuses nearby see pricing pressure on enterprise tenants
- High churn (>7% annual) suggests moat is weaker than claimed

## Red Flags Specific to Colo

- Annual churn >8%: structural, not cyclical — requires explanation
- Interconnection revenue declining as % of total: highest-margin line being displaced
- 33%+ of ARR expiring in current year without renewal data disclosed: renewal cliff risk
- Power costs not passed through to customers (power market risk)
- Finance leases excluded from leverage calculation without disclosure (hidden leverage)
- ABS ARDs (2029-2032) approaching without refinancing plan disclosed
