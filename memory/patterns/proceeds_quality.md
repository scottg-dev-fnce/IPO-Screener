---
name: proceeds-quality-rf19
type: pattern
version: 1
last_written: 2026-07-08
source_analysis: csquare_inc_amendments_1_2_original
confidence: medium
observations: 1
expires: never
---

# RF-19 Proceeds Quality — Cross-Sector Patterns

## Threshold Levels and What They Signal

| Non-Operational % | Signal | Typical Structure |
|---|---|---|
| 30-50% | Moderate — mixed use | Partial debt paydown + growth capex |
| 50-70% | High — balance sheet repair | PE-structured, revolver-heavy |
| 70-90% | Very high — recapitalization | ABS platform, near-term maturity forcing function |
| >90% | Extreme — pure refinancing event | Sponsor bridge recovery; investor funding a PE recap |

Csquare Amendment No. 2: **98.6%** — the high end of observed range.

## The Forcing Function Pattern

PE-backed IPOs use a **near-term debt maturity as the IPO forcing function**. Look for:
1. Revolving credit facility maturing within 12 months of IPO date
2. The revolver is first use of proceeds (immediately removes refinancing overhang)
3. Narrative in "Liquidity and Capital Resources" emphasizes revolver maturity

When you see this: the IPO is being driven by refinancing necessity, not growth opportunity. Price accordingly (VA penalty justified).

## Adversarial vs. Defensive Uses

**Adversarial (sponsor recovery):**
- Paying off Promissory Note held by the sponsor (Brookfield pattern)
- Paying off PIK or PIK-toggle debt — sponsor collected accrued interest during PE hold
- Secondary shares to selling shareholders while company has negative cash flow

**Defensive (investor benefit):**
- Paying off revolver before maturity (removes near-term liquidity cliff)
- Paying off floating-rate debt in rising rate environment
- Paying off highest-cost debt tranches (≥7% fixed rate) while retaining cheapest tranches

**Anomaly to flag:** Paying off the **cheapest long-term debt** (e.g., 2.50% fixed ABS notes due 2050) with equity capital at 6%+ cost. Economically counterintuitive — look for structural reason (credit profile improvement for future refinancings).

## Assessment Framework (proceeds_quality_assessment field)

Always address these 5 questions in the assessment:
1. Which debt instruments are being retired and why were they chosen?
2. Is there a revolver maturity within 12 months (defensive) or is this purely sponsor recovery (adversarial)?
3. What is the post-IPO interest coverage ratio?
4. Does any repayment benefit a related party? (Sponsor Promissory Note = red flag)
5. What's the post-repayment capital structure — is the remaining debt manageable?

End with a single verdict sentence: either "Legitimate deleveraging of [structure], though [caveat]" or "Primarily a sponsor recapitalization event dressed as an IPO."

## Scoring Note

RF-19 deducts −2.5 from M&G (not from FHR). This is intentional — it's a governance/alignment issue (proceeds don't benefit public investors operationally), not a financial health issue per se. The leverage risk is captured separately in RF-14.
