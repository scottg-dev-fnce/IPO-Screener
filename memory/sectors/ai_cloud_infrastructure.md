---
name: ai-cloud-infrastructure
type: sector
version: 1
last_written: 2026-07-08
source_analysis: coreweave_inc_pass
confidence: medium
observations: 1
expires: never
---

# AI Cloud Infrastructure — Scoring Framework

SIC 7370 (Computer Services). Observed: CoreWeave, Inc. (CRWV, PASS 54.0 → displayed 49.0 post-RF-20, despite BMQ=8.5 and MCP=8.5).

## The Core Tension: Exceptional Business, Problematic Deal Structure

CoreWeave is the defining case study. Business fundamentals: $1.9B revenue, 737% YoY growth, 74% gross margins, $11.55B OpenAI MSA, $15.1B remaining performance obligation. BMQ and MCP both scored 8.5. **Still PASS.**

Why: RF-19 CRITICAL (65% of proceeds to debt), RF-14 HIGH (Leveraged Issuer), RF-02 HIGH (customer concentration — likely Microsoft/OpenAI), RF-06 HIGH (governance), RF-25 HIGH (accounting), RF-09 HIGH (related party). The deal structure consumed an otherwise exceptional business.

**Key lesson:** In AI cloud infra, the business model and market position can be near-perfect. The killer is almost always the deal structure inherited from venture/PE financing. Check the following before scoring BMQ/MCP optimistically:
1. Customer concentration — GPU cloud often has 1-3 hyperscalers as anchor customers
2. Leverage from GPU financing (debt to fund GPU purchases at $10K-$40K/GPU)
3. Governance — if Nvidia or a large hyperscaler has a board seat, RF-06 can fire

## Valuation Framework

- **Primary metric:** EV/Revenue (growth-stage; EBITDA often not yet meaningful or manipulated by GPU depreciation)
- **Secondary:** Forward EV/EBITDA
- **Sector range:** Wide — 8-25x NTM Revenue for high-growth AI infra in current market
- **GPU cloud specific:** depreciation of GPU assets (3-4 year useful life on $30K/GPU) creates massive D&A load. Adj. EBITDA adds back D&A. Verify whether D&A add-back is reasonable or hides real economics.
- **Customer revenue visibility:** RPO (Remaining Performance Obligation) and MSA backlog are the key valuation anchors; compare RPO/EV as a proxy for revenue visibility multiple

## Key Metrics to Pull

| Metric | What to check |
|---|---|
| GPU count and utilization | 250K+ GPUs; utilization >90% at scale |
| Gross margin | 70%+ for software-defined; 40-60% for pure GPU rental |
| NRR | AI cloud should be >120% if expansion is real |
| Customer concentration | Top 3 customers as % of revenue |
| RPO / Remaining Performance Obligations | Revenue backlog visibility |
| GPU financing structure | Operating leases vs. debt vs. owned; what's on balance sheet |

## RF Risk Pre-Set for AI Cloud

- **RF-02:** Almost always triggers (GPU cloud → hyperscaler/AI lab anchor = concentration)
- **RF-14:** Common — GPU capex financed with debt at high leverage
- **RF-19:** High risk — if NVIDIA or venture investors sold shares or company repays GPU financing with IPO proceeds
- **RF-06:** Check for Nvidia equity ownership (they have strategic stakes in many GPU cloud companies)
- **RF-25:** Aggressive accounting on GPU depreciation useful lives, revenue recognition on MSAs

## What Would Make an AI Cloud UNDERWRITE

- Customer diversification (no customer >20% of revenue)
- Conservative leverage (net debt/EBITDA <4x after IPO)
- Proprietary software layer (not just GPU rental — competitive moat beyond raw compute)
- Gross margins >70% (indicates software-defined value, not just hardware pass-through)
- Governance: no hyperscaler strategic investor with board seat
