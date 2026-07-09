---
name: brookfield-asset-management
type: sponsor
version: 1
last_written: 2026-07-08
source_analysis: csquare_inc_amendments_1_2_original
confidence: high
observations: 3
expires: never
---

# Brookfield Asset Management — Deal Playbook

Observed across 3 Csquare, Inc. filings (original S-1, Amendment No. 1, Amendment No. 2). This is the canonical Brookfield infrastructure IPO structure.

## Capital Structure: The ABS Playbook

Brookfield platforms use **ABS (Asset-Backed Securities) via bankruptcy-remote SPEs** as primary debt instrument. Never corporate high-yield or investment-grade bonds.

- Entity structure: `[Platform] Issuer LLC` + `[Platform] Co-Issuer LLC` (two SPEs, EDGAR will show separate CIK if searched)
- Debt is ring-fenced at asset level; no corporate guarantee on parent IPO entity
- Multiple ABS series issued in rapid succession during the PE hold period (Csquare: 5 series in 14 months)
- Each series has an **Anticipated Repayment Date (ARD)** 5-7 years out; legal final maturity 25-30 years out — creates a "soft wall" not a hard maturity
- ABS notes priced at 5-6% fixed in current rate environment
- **Variable Funding Note (VFN)** is the revolving piece within the ABS stack; floating-rate (SOFR+); Canadian banks (TD, BMO, Scotia) typically hold this tranche and are hence triple-conflicted as underwriters

## The Revolver-as-Forcing-Function Pattern

Brookfield always includes a **revolving credit facility with a near-term maturity** (Dec of the IPO year). This creates IPO urgency narrative: "if we don't IPO now, the revolver matures." Revolver is the first use of proceeds ($700M-$1B range typical for large infra IPOs).

- Check revolver maturity date in "Debt Summary" table — if it's within 12 months of IPO, this is the forcing function
- Revolver admin agent: typically Wells Fargo (also conflicted underwriter)

## The Promissory Note Pattern (Recapture Mechanism)

Brookfield issues a **PIK-capable Promissory Note to itself** from the platform entity in the 60-90 days before IPO. Csquare: $75M at 3.54%, issued May 14, 2026, repaid from IPO proceeds.

- Function: recapture cash from the platform pre-IPO at favorable PIK rate
- Gets repaid via IPO proceeds along with the revolver → Brookfield recovers both sponsor bridge capital AND underwriting fees simultaneously
- Always check "Indebtedness" section for any notes payable to the Stockholder/parent entity added within 90 days of S-1 filing date

## Underwriting Syndicate: The Canadian Bank Cluster

Every Brookfield infrastructure IPO includes a cluster of **6 Canadian banks** to cover Canadian institutional distribution:
- TD Securities (almost always co-lead representative)
- BMO Capital Markets
- Scotia Capital (USA)
- CIBC World Markets
- National Bank of Canada Financial
- RBC Capital Markets (often serves as QIU per FINRA 5121)

These banks are triple-conflicted: revolver lenders + VFN holders + underwriters. FINRA Rule 5121 conflicts are always disclosed; QIU is always RBC (most independent of the 6 Canadian banks). Expect **RF-20 to trigger on every Brookfield deal** due to Canadian bank cluster alone.

**Brookfield Securities LLC** always appears as co-manager with FINRA 5121 conflict (affiliate owns >10% equity). Cannot confirm discretionary account sales without written approval.

## Governance: The Controlled Company Playbook

- Brookfield retains **majority of board** via Stockholders Agreement nomination rights (proportionate to ownership)
- Veto rights remain active until Brookfield drops below **20% ownership** — expect 2-3 secondary offerings before governance improves
- Board Chairman is always a Brookfield VP or Managing Partner (Csquare: John Hellmann, Brookfield VP)
- NYSE controlled company: Brookfield elects to waive majority-independent board, independent compensation committee, independent nominating committee
- Registration rights granted for underwritten secondaries — model secondary supply at 6-9 months post lockup expiry

## Management Loan Pattern

Brookfield affiliate issues loans to senior management (CEO, CFO, CLO, COO) approximately **12-18 months before IPO**, then extinguishes them pre-filing.

- Purpose: align management economically during PE hold period; creates tax-efficient compensation
- Always disclosed in related party section; always "extinguished prior to filing"
- Check amounts: CEO typically $4-8M, C-suite $400K-$700K each
- Not a red flag per se; standard Brookfield governance practice — but confirms timeline to IPO was planned well in advance

## Pre-IPO Acquisition Pattern

Brookfield platforms typically do a **bolt-on acquisition 6-12 months before IPO** from another Brookfield-affiliated entity:
- Csquare: Compass Datacenters (10 sites, Oct 2025, 49% Brookfield-owned seller)
- Creates: additional debt (new ABS issuance), goodwill, and a related-party acquisition disclosure
- Purpose: scale the platform to IPO-worthy size; Brookfield recycles capital from partial-ownership positions
- Check acquisition terms for bargain purchase gain (Csquare FY2024: $544.1M bargain gain from 2024 Portfolio Acquisition) — this distorts GAAP income in the acquisition year

## Scoring Implications

On any Brookfield-backed deal, pre-load these deductions:
- RF-06 HIGH (governance — controlled company, no independent board): −2.5 M&G
- RF-09 MEDIUM (related party — pervasive Brookfield entanglement): −1.5 M&G
- RF-19 HIGH (proceeds quality — revolver + Promissory Note retirement): −2.5 M&G
- RF-20 POST-HOC: almost certain given Canadian bank cluster (13+ underwriters typical)
- Leveraged Issuer flag: virtually guaranteed (ABS stack always produces >5x Debt/Adj.EBITDA on GAAP-loss entity)
- SCORING FLOOR: expect 4+ HIGH flags → floor at 64 → CONDITIONAL_HEAVY is the baseline unless BMQ+MCP both ≥8.5
