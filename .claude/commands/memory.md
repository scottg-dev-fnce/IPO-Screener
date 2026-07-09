# /memory — IPO Screener Analysis Memory System

Manages the project-local memory system at `~/IPO_Screener/memory/`.
Arguments: $ARGUMENTS

## Sub-Command Routing

Parse the first word of $ARGUMENTS to determine the sub-command:
- `write` → WRITE flow
- `read` → READ flow (optional topic after "read")
- `outcome` → OUTCOME flow
- `list` → LIST flow
- `diff` → DIFF flow
- `rollback` → ROLLBACK flow
- No argument or unrecognized → show HELP

---

## WRITE flow

**Step 1 — Determine what to write.**
Based on the current session context, identify 1-3 memory files that should be updated. Prefer updating existing files over creating new ones. New files only when a genuinely new sector or sponsor is being added.

Valid target types:
- `sectors/{sector-slug}.md` — sector-specific patterns
- `sponsors/{sponsor-slug}.md` — PE/sponsor deal playbooks
- `patterns/{pattern-slug}.md` — cross-sector analytical patterns
- `outcomes/{company-slug}.md` — post-IPO performance data
- `calibration/scoring_drift.md` — calibration log entries

**Step 2 — Draft proposed content.**
Write the proposed addition or change. Follow the file format:
- Frontmatter YAML block with: name, type, version (increment by 1), last_written (today's date), source_analysis (slug of the analysis that triggered this), confidence (low/medium/high), observations (count), expires (date or "never")
- Content in markdown sections
- Maximum 500 words per file (soft cap — if file would exceed this, compress first)

**SECURITY RULES — enforce strictly:**
- Include ONLY patterns derived from publicly available SEC filings or market data
- NO personal information, credentials, API keys, email addresses, internal firm names, trading positions, or client-sensitive data
- NO verbatim text copied from filings — synthesize the pattern in your own words
- The repo is PUBLIC — treat every word as publicly visible
- If proposed content contains anything that might be sensitive, flag it and remove it before showing to the user

**Step 3 — Show the diff to the user.**
Display the proposed changes clearly. Show the current version (if file exists) vs. proposed version. Ask: "Approve this memory write? (yes to commit / no to cancel / edit to modify)"

**Step 4 — Wait for approval. Do NOT write until the user approves.**
If approved: write the file, increment version number, update MEMORY_INDEX.md if it's a new file, then run:
```bash
cd ~/IPO_Screener && git add memory/ && git commit -m "memory: update [filename] (v[N]) — [one-line description]"
```
If rejected: discard the proposed content and confirm cancellation.

---

## READ flow

Read the MEMORY_INDEX.md first. Then load specific files relevant to the topic in $ARGUMENTS.

If no topic given: read MEMORY_INDEX.md and summarize what's available.
If topic given: match against index entries and load the 1-3 most relevant files.

Display: file name, version, confidence, key patterns that apply to the current analysis.

---

## OUTCOME flow

Record post-IPO performance data for a previously analyzed company.
Format from $ARGUMENTS: `outcome [company-slug] [price-data]`

Target file: `memory/outcomes/{company-slug}.md`

Entry format:
```markdown
---
name: {company-slug}-outcomes
type: outcome
version: 1
last_written: {today}
source_analysis: post_ipo_tracking
confidence: high
observations: 1
expires: never
---

# {Company Name} ({TICKER}) — Post-IPO Outcomes

| Metric | Value |
|---|---|
| IPO date | |
| IPO price | |
| Our recommendation | |
| Our score | |
| 30d price / return | |
| 90d price / return | |
| 180d price / return | |
| Key divergence | |
| Calibration signal | |
```

Then append a summary row to `calibration/scoring_drift.md` pending table.

SECURITY: outcome files contain only publicly available market data (stock prices, dates). No internal data.

Show proposed content to user, require approval, then commit.

---

## LIST flow

Read MEMORY_INDEX.md and list all files with: name, type, version, confidence, observation count.
Format as a table. Identify any files that may need updating (low confidence + 1 observation, or expired dates).

---

## DIFF flow

Format from $ARGUMENTS: `diff [filepath]`
Run: `git log --oneline -5 -- memory/[filepath]` to show recent commits.
Run: `git diff HEAD~1 HEAD -- memory/[filepath]` to show the last change.
Display both outputs.

---

## ROLLBACK flow

Format from $ARGUMENTS: `rollback [filepath]`

Show the user what the previous version contained:
```bash
git show HEAD~1:memory/[filepath]
```

Confirm: "Roll back memory/[filepath] to the previous version? This will overwrite the current version. (yes / no)"

If approved:
```bash
cd ~/IPO_Screener && git checkout HEAD~1 -- memory/[filepath] && git add memory/[filepath] && git commit -m "memory: rollback [filepath] to prior version"
```

---

## HELP (no sub-command)

Display this usage guide:

```
/memory write              Propose and commit a memory update (requires approval)
/memory read [topic]       Load relevant memory files for the current analysis
/memory outcome [co] [data] Record post-IPO performance data
/memory list               Show all memory files with version and confidence
/memory diff [file]        Show what changed in the last write to a file
/memory rollback [file]    Restore a file to its previous version

Security: all memory files are public. Never include personal info or credentials.
```
