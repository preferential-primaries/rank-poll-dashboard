# Adding a future poll

The dashboard is static data plus a build script. A new poll goes through
the same coding as the historical three, so it lands in the dashboard with
identical tribe scores, ideology, and ballot tables.

## 1. Export from JotForm

In the JotForm submission table for the new poll, export CSV **with the
Submission ID and Submission IP columns checked** in the export dialog
(they are off by default — without IDs, responses can't be joined to
rankings or de-duplicated later). Save it in a **local `raw/` folder**
next to the repo checkout (or set `RCV_RAW_DIR` to its location).
`raw/` is gitignored: raw exports contain respondent IPs and must **never**
be committed. Only the coded outputs (no IPs, no emails) go in the repo.

## 2. Register the poll in the builder

In `scripts/build_unified.py`, add one line to `SOURCES`:

```python
("MmmYYYY", os.path.join(FRESH, "<file>.csv")),
```

`poll_source` labels use the pattern `Feb2026`, `Apr2026`, `Aug2026`
(month the poll ran + year). The dashboard displays them via `POLL_LABEL`
in `index.html` — add the new label there too.

## 3. Map the new form's columns

`code_respondent()` finds columns by substring. Check each of these for the
new form and adjust if the wording changed:

- **Policy priorities** — matched on `"priorities as a"`. If the form
  ranks priorities (like Aug), set `ranked = True` for that poll (currently
  `ranked = poll == "Aug2026"`); if it is pick-up-to-N (like Feb/Apr),
  picks get equal weights.
- **New policy options** — any option text not in `POLICY_TEXT_TO_KEY` is
  silently ignored. If the form adds an option, add its text and a
  10-number affinity vector to `POLICY_AFFINITY` first (same tribe order).
- **Ideology scale** — if the form uses 1–5, add a rescale entry like
  `FEB_RESCALE`. If it uses 1–7, nothing is needed. The worded label
  (`ideology_label`: 1 Very Liberal … 7 Very Conservative) is derived
  automatically from `IDEOLOGY_LABELS`.
- **GOP ranking** — matched on `"Republican Presidential Nomination"` or
  `"2028 GOP nominee"`. New candidates just appear; add current-field
  names to `CURRENT_GOP_FIELD` if they belong in the "current field" set.
- **Election concerns** — a ranked top-3 question feeds the 1% election
  component automatically if its header contains
  `"Election Integrity Concern"` and its options match `ELECTION_AFFINITY`
  keys. A multi-select statement question (like Apr) is stored as
  selections only and does not feed tribe scores.
- **Poll-specific questions** (Senate, Iran, tariffs, etc.) — add a branch
  in `code_respondent()` and a column in the CSV field list if the
  dashboard should cross-tab on them.
- **Top 3 and denominators** — automatic, no manual step. The builder
  flags `top3` on every ranking row, records each respondent's top-3
  list, and writes `candidate_availability.json` (which candidates each
  poll offered). The dashboard's %s use the offered-respondents
  denominator from that file, so a candidate only offered in one poll is
  never measured against all polls.

## 4. Build, validate, publish

```bash
cd scripts
python3 build_unified.py          # rebuilds unified_*.csv/json
python3 build_dashboard_data.py   # rebuilds dashboard data/*.json
```

Check the console output: respondent counts per poll, tribe distribution,
and any unmapped policy options (add a print in `code_respondent()` if you
suspect silent drops). Then commit `data/`, `scripts/`, and `index.html`
(if labels changed) and push — GitHub Pages rebuilds automatically.

## 5. Validation (recommended for the first new poll)

If the poll also flows through a live Apps Script pipeline with a
Respondents table, compare the builder's tribe scores against it the same
way the historical polls were validated (see `validation_report.json` in
the project workspace): join on Submission ID and check mean absolute
difference. August 2026 reproduced the live script exactly (180/180
scores identical); a new poll built from the same code should too.
