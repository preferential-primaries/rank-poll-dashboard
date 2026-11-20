# RCV Polling Dashboard

Unified reporting dashboard for ranked-choice-voting polls of the 2028 GOP
presidential nomination (and related contests), built from JotForm exports.

**Live dashboard:** https://preferential-primaries.github.io/rank-poll-dashboard/

## What's here

- `index.html` — the dashboard (static page; no build step)
- `data/` — the unified dataset
  - `respondents.json` — one record per respondent (1,439 as of Nov 20, 2026),
    including each respondent's top-3 candidates and worded ideology label
  - `gop_rankings.json`, `dem_rankings.json` — ranked ballots, by respondent
    (each entry carries a `top3` flag for ranks 1–3)
  - `meta.json` — poll inventory, candidates, tribes, model note, and the
    per-poll ballot (`gop_offered` / `dem_offered`)
  - `candidate_availability.json` — which candidates each poll offered;
    this drives the dashboard's per-candidate denominators
  - `unified_*.csv` — the same dataset in archival CSV form
- `scripts/build_unified.py` — builds the unified dataset from raw JotForm
  exports (tribe coding, ideology rescaling, ranking normalization)
- `scripts/build_dashboard_data.py` — compacts the unified dataset into the
  dashboard's JSON files
- `docs/APPEND.md` — how to add a future poll

## Polls included

| Poll | n | Dates | Notes |
|------|---|-------|-------|
| Feb 2026 | 1,093 | Jan 26 – Sep 25, 2026 | 12-candidate GOP ballot; 1–5 ideology; pick-up-to-4 priorities |
| Apr 2026 (TX) | 327 | Mar 26 – May 26, 2026 | TX Senate run-off + 5-candidate presidential ballot; Iran, tariffs, election statements |
| Aug 2026 | 19 | Jul 22 – Aug 6, 2026 | 9-candidate GOP ballot + 9-name Democratic ballot; ranked election concerns |

## Tribe model

Tribe scores follow the live presidential model, applied uniformly to all
polls: 90% policy priorities + 9% ideology + 1% election signal (August
only), renormalized over the components present. Candidate rankings are never
used for tribe classification. See `docs/APPEND.md` and the dashboard's
Data & methods tab for recoding notes.

## Privacy

No names, emails, or IP addresses are in this repo — only opaque submission
IDs, states, and demographic bands.
