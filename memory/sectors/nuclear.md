---
name: advanced-nuclear-fuel-manufacturing
type: sector
version: 1
last_written: 2026-07-08
source_analysis: standard_nuclear_inc_amendment_analysis
confidence: low
observations: 1
expires: never
---

# Advanced Nuclear Fuel Manufacturing (TRISO / SMR Supply Chain)

SIC 2819 (Industrial Inorganic Chemicals). Emerging sector; limited public comparables. One observation (Standard Nuclear, Inc.).

## Business Model

TRISO fuel (Tristructural-Isotropic): uranium oxide particles coated in multiple ceramic/carbon layers, embedded in graphite matrix. Key properties: handles temperatures HALEU reactors cannot; proliferation-resistant; can be shaped into "pebbles" or "compacts."

- **Customer base:** Advanced reactor developers (SMRs, microreactors) — themselves pre-commercial
- **Revenue model:** DOE grants + development contracts; commercial fuel supply contracts are the eventual payoff
- **Critical dependency:** Customers must successfully build and license their reactors before TRISO demand materializes; TRISO manufacturer's commercial success is contingent on their customers' success
- **Lead time:** 5-10 years from IPO to material commercial revenue in best case

## Key Pre-Commercial Metrics to Pull

| Metric | What to Check |
|---|---|
| DOE grants awarded (amount + stage) | Higher DOE commitment = more de-risked |
| Manufacturing facility status | Design / Permitted / Under construction / Operational |
| Letters of intent / MOUs | Do any have committed volumes and pricing? |
| Fuel qualification status | NRC qualification is the gating item |
| Customer reactor timeline | If customers slip, commercial revenue slips |

## Valuation Framework

- **No revenue/EBITDA multiple applies** — pre-commercial; use risk-adjusted NPV or comparable private funding rounds
- PRICE-PENDING rule likely applies: price range absent in early S-1 filings is common for pre-commercial issuers testing market appetite
- RF-22 (small firm suitability) threshold check: if TTM revenue <$10M, RF-22 is close to triggering — verify offering size
- Comparable: government contractor / specialty chemical manufacturer multiples are the floor; DOE program optionality is the ceiling
- EV/Revenue TTM: not meaningful pre-commercial; document `revenue_pre_commercial_ttm_usd_millions` to avoid schema validator false positive (rename field from `revenue_ttm_usd_millions`)

**Schema note:** The memo validator flags `revenue_ttm_usd_millions < 1000` as a likely unit error for non-PASS recommendations. Pre-commercial issuers with genuine sub-$10M revenue must rename the field to `revenue_pre_commercial_ttm_usd_millions` to bypass the false positive.

## Scoring Implications

Pre-commercial nuclear fuel manufacturers will almost always score CONDITIONAL (50-65) due to:
- RF-05 HIGH (runway risk — burn rate vs. grant/contract income vs. commercial timeline)
- RF-25 potential if accounting policies are aggressive (grant revenue recognition, capitalization of development costs)
- MCP is the strongest dimension (if DOE is backing them, that is a signal of unique technical capability)
- FHR is the weakest dimension (pre-revenue, negative operating cash flow, grant-dependent)
- VA is constrained — hard to underwrite vs. comps when there are no comps

## Regulatory & NRC Considerations

- NRC fuel qualification process is long (3-7 years) and adds timeline risk
- NQA-1 (Nuclear Quality Assurance) requirements govern manufacturing; QA failures can delay or halt production
- HALEU (High-Assay Low-Enriched Uranium) supply chain is a dependency — enrichment capacity is limited and mostly DOE-controlled currently
- Export controls (NRC export licenses) required for international fuel supply — regulatory overhang risk
