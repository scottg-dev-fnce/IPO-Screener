---
name: pe-exit-structure
type: pattern
version: 1
last_written: 2026-07-08
source_analysis: csquare_itg_coreweave
confidence: high
observations: 3
expires: never
---

# PE-Backed IPO Exit Structure — Cross-Sector Patterns

Observed across: Csquare (Brookfield/ABS), ITG (Oaktree/infrastructure services), CoreWeave (Magnetar+Nvidia/GPU cloud). The debt structure differs; the exit pattern is identical.

## The Forcing Function: Revolver Maturity

PE-backed IPOs almost always have a **revolving credit facility maturing within 12 months of IPO**. This creates the urgency narrative and is the first use of proceeds. Check "Debt Summary" or "Indebtedness" table for any revolver with a maturity date within 12-18 months of the S-1 filing date. That is the forcing function; the IPO is not opportunistic timing — it is a mandated refinancing event.

## Proceeds Percentage to Debt (Reference Points)
- Csquare: 98.6% to debt (extreme — pure recap)
- CoreWeave: 65.2% to debt (still very high — RF-19 CRITICAL in that case)
- ITG: ~70%+ to debt (Oaktree leverage unwind)
- Any deal >50% to debt: RF-19 triggers; >80%: investors are funding a recapitalization, not a business

## The ABS Debt Pattern

Large PE infrastructure platforms (data centers, telecom/fiber, power generation) use **ABS financing via bankruptcy-remote SPE entities** rather than corporate bonds:
- Look for `[Company] Issuer LLC` and `[Company] Co-Issuer LLC` entities in the filing
- ABS notes have Anticipated Repayment Dates (ARDs) 5-7 years out; legal final maturity 25-30 years
- Variable Funding Note (VFN) is the floating-rate revolving piece within the ABS stack
- Revolver is separate from ABS; the VFN is often confused with the revolver in disclosure

## The Sponsor Bridge / PIK Loan Pattern

In the 60-90 days before S-1 filing, look for a **Promissory Note or bridge loan payable to the controlling shareholder** added to the indebtedness table. This is the sponsor recapturing value pre-IPO: they lend to the company at a PIK-capable rate, then recover that loan from IPO proceeds alongside underwriting fees.

Signal: indebtedness table has a note added within 90 days of S-1 date where the lender is the majority shareholder, a managing member, or a "Stockholder" entity. Always check the lender identity.

## Pre-IPO Bolt-On Acquisition Pattern

PE platforms often do a **related-party bolt-on acquisition 6-12 months before IPO** from another entity they partially own. This creates: (a) new ABS debt, (b) goodwill, (c) RF-09 related-party disclosure. The acquisition simultaneously increases platform scale to IPO-worthy size and allows the PE firm to recycle capital from partial-ownership positions at favorable valuations. Look for "Acquisition" named entities in recent S-1 notes to financial statements.

## Scoring Pre-Set for PE Exits

When you identify a PE-backed leveraged IPO:
- RF-14 HIGH: leverage >5x almost guaranteed (deduct −2.5 FHR)
- RF-19 HIGH: proceeds to debt >50% almost guaranteed (deduct −2.5 M&G); requires `proceeds_quality_assessment`
- RF-06 HIGH: sponsor board control and veto rights (deduct −2.5 M&G)
- RF-09 MEDIUM: related-party transactions (deduct −1.5 M&G)
- Leveraged Issuer flag: check GAAP-loss + Debt/EBITDA >5x → FHR weight to 20%, VA to 15%
- Scoring floor: 4+ HIGH flags → floor ≤64 unless BMQ and MCP both ≥8.5
- Starting point before business model evaluation: M&G starts at 72.5 (10.0 base − 6.5 flag deductions); FHR starts at 55.0 after RF-14 on a pre-IPO leveraged structure
