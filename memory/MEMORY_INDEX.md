# IPO Screener — Analysis Memory Index

Auto-loaded at the start of every session. One-line per entry.
Load the full file only when the topic is relevant to the current analysis.
**Do NOT write to any memory file during S-1 analysis. Use `/memory write` after analysis is complete.**

## Sectors

- [Carrier-Neutral Colocation](sectors/colocation.md) — ABS vs. corporate debt structures, churn metrics, ARS 606/842 dual-framework, EV/Adj.EBITDA 18-30x valuation range, brownfield capex norms. v1. HIGH (1 obs).
- [Advanced Nuclear Energy](sectors/nuclear.md) — TRISO fuel + HTGR reactors, DOE grant signals, NRC timeline, HALEU supply chain, customer agreement quality hierarchy, schema revenue field rename note. v2. MEDIUM (2 obs).
- [Enterprise SaaS](sectors/enterprise_saas.md) — Rule of 40 ≥50 threshold, NRR ≥130%, EV/Revenue valuation, UNDERWRITE vs CONDITIONAL vs PASS criteria, dual-class governance treatment. v1. MEDIUM (1 obs).
- [Clinical-Stage Biotech](sectors/biotech_clinical.md) — UNDERWRITE requires Phase 2b data + BTD + validated partnership + management track record; FHR driven by runway-to-catalyst analysis; RF-01A/B going concern patterns. v1. MEDIUM (1 obs).
- [AI Cloud Infrastructure](sectors/ai_cloud_infrastructure.md) — CoreWeave case: BMQ/MCP can be 8.5+ yet PASS due to deal structure; GPU financing leverage, customer concentration, GPU depreciation accounting. v1. MEDIUM (1 obs).
- [Defense Technology](sectors/defense_tech.md) — HawkEye/Elmt: high BMQ/MCP but VA=3-4 due to valuation disconnect; government concentration RF-02; POC revenue recognition risk RF-25; ITAR limits TAM. v1. MEDIUM (2 obs).

## Analytical Patterns

- [Proceeds Quality — RF-19](patterns/proceeds_quality.md) — forcing function revolver pattern, adversarial vs. defensive uses, 5-question assessment framework, non-operational % benchmarks by deal type. v1. MEDIUM (1 obs).
- [PE Exit Structure](patterns/pe_exit_structure.md) — revolver-as-forcing-function, ABS SPE debt, sponsor bridge/PIK loan pattern, pre-IPO bolt-on acquisition, pre-set deductions for leveraged PE exits. v1. HIGH (3 obs: Csquare, ITG, CoreWeave).

## Outcomes & Calibration

- [Scoring Drift Log](calibration/scoring_drift.md) — post-IPO outcome tracking. 0 entries. Pending: CSQR, STDN.
- `outcomes/` — per-company outcome files. Empty until post-IPO trading data available.

## Loading Guide

| Trigger | Load |
|---|---|
| Data center / colo / ABS infra | sectors/colocation.md |
| Nuclear fuel or reactor design | sectors/nuclear.md |
| Software / SaaS / platform | sectors/enterprise_saas.md |
| Biotech / pharma / clinical stage | sectors/biotech_clinical.md |
| AI compute / GPU cloud | sectors/ai_cloud_infrastructure.md |
| Defense / government contracts | sectors/defense_tech.md |
| PE-backed, leveraged issuer, >50% proceeds to debt | patterns/pe_exit_structure.md |
| RF-19 triggered or proceeds >30% to debt | patterns/proceeds_quality.md |

## Security Rules

- All memory files contain only patterns derived from **publicly available SEC filings**
- No personal information, credentials, firm-internal data, or trading positions
- This repo is **public** — treat every word as publicly visible
- Writes require `/memory write` with explicit user approval; all writes are git-committed
- Rollback: `/memory rollback [file]` or `git checkout HEAD~1 -- memory/[file]`
