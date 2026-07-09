# IPO Screener — Analysis Memory Index

Auto-loaded at the start of every session. One-line per entry.
Load the full file only when the topic is relevant to the current analysis.
Do NOT write to any memory file during S-1 analysis. Use `/memory write` after analysis is complete.

## Sponsors
- [Brookfield Asset Management](sponsors/brookfield.md) — ABS playbook, Canadian bank cluster, Promissory Note recapture, management loans, controlled company governance. v1. Confidence: HIGH (3 observations).

## Sectors
- [Colocation Data Centers](sectors/colocation.md) — carrier-neutral colo, ABS vs corporate debt, churn metrics, valuation framework (EV/Adj.EBITDA 18-30x), brownfield capex, ASC 606/842 dual-framework. v1. Confidence: HIGH (1 observation).
- [Advanced Nuclear Fuel (TRISO/SMR)](sectors/nuclear.md) — pre-commercial stage, DOE grants, NRC qualification timeline, HALEU supply chain, schema note on revenue field renaming. v1. Confidence: LOW (1 observation).

## Analytical Patterns
- [Proceeds Quality — RF-19](patterns/proceeds_quality.md) — forcing function pattern, adversarial vs defensive uses, assessment framework, 5-question checklist. v1. Confidence: MEDIUM (1 observation).
- [Syndicate Risk — RF-20](patterns/syndicate_risk.md) — FINRA 5121 conflict types, dual-conflict test, QIU selection logic, Canadian bank cluster, post-hoc penalty calculation. v1. Confidence: MEDIUM (1 observation).

## Outcomes & Calibration
- [Scoring Drift Log](calibration/scoring_drift.md) — post-IPO outcome tracking. 0 entries. Pending: CSQR, STDN.
- outcomes/ — individual company outcome files. Empty until post-IPO data available.

## Loading Guide
| Trigger | Load |
|---|---|
| Issuer is PE/sponsor-backed | Relevant sponsor file |
| Sector matches a sector file | That sector file |
| RF-19 triggered | patterns/proceeds_quality.md |
| >6 underwriters or FINRA 5121 conflicts | patterns/syndicate_risk.md |
| Post-IPO data available | calibration/scoring_drift.md + relevant outcomes/ file |

## Security Rules (enforced by /memory skill)
- Memory files contain only patterns derived from publicly available SEC filings
- No personal information, credentials, firm-internal data, or trading positions
- No auto-writes during analysis — only via explicit `/memory write` with user approval
- All writes are git-committed with version bump; rollback via `git checkout HEAD~1 -- memory/[file]`
- Public repo: treat every memory file as publicly visible
