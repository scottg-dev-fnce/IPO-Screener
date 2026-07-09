---
name: scoring-drift-calibration
type: calibration
version: 1
last_written: 2026-07-08
source_analysis: initial-setup
confidence: low
observations: 0
expires: never
---

# Scoring Drift & Calibration Log

Tracks systematic over- or under-scoring patterns as post-IPO outcomes are observed.
No entries yet — populate via `/memory outcome [company] [data]` as post-IPO data becomes available.

## Format for Entries

```
## [Company] [Ticker] — [IPO Date]
- **Our score:** [X] [RECOMMENDATION]
- **Actual 30d return:** [%]
- **Actual 90d return:** [%]
- **Actual 180d return:** [%]
- **Key divergence:** [What we got wrong or right]
- **Calibration signal:** [Which flag was over/under-weighted?]
- **Added:** [Date]
```

## Systematic Patterns (populated as observations accumulate)

*No entries yet. Minimum 5 outcomes needed before drawing calibration conclusions.*

## Pending Outcomes to Track

| Company | Ticker | Our Rec | Our Score | IPO Date | 30d | 90d | 180d |
|---|---|---|---|---|---|---|---|
| Csquare, Inc. | CSQR | CONDITIONAL_HEAVY | 64.0 (59.0 post-RF20) | TBD | — | — | — |
| Standard Nuclear, Inc. | STDN | CONDITIONAL | 55.0 | TBD | — | — | — |

## Calibration Rules (once 5+ outcomes exist)

- If UNDERWRITE recommendations average <+10% at 90d: BMQ/MCP weights may be too generous
- If PASS recommendations average >-10% at 90d: RF thresholds may be too conservative
- If CONDITIONAL_HEAVY recommendations cluster near 0% at 90d: floor at 64 is well-calibrated
- If RF-14 (leverage) companies consistently underperform: leverage deduction (-2.5 FHR) may be too small
