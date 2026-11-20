#!/usr/bin/env python3
"""Prepare compact dashboard data files from the unified dataset.

Reads ~/workspace/rcv-polling/unified/unified_*.json|csv and writes:
  ~/workspace/rcv-polling/dashboard/data/respondents.json  (compact, full records)
  ~/workspace/rcv-polling/dashboard/data/gop_rankings.json (parallel array:
      gop[i] = [[candidate_index, rank, in_current_field], ...] for respondent i)
  ~/workspace/rcv-polling/dashboard/data/dem_rankings.json (same shape)
  ~/workspace/rcv-polling/dashboard/data/meta.json          (polls, candidates,
      tribes, date range, counts, model note)
"""
import csv
import json
import os
import collections

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "data")  # unified_*.csv/json live here
DST = os.path.join(REPO, "data")  # dashboard JSONs live here too
os.makedirs(DST, exist_ok=True)

respondents = json.load(open(os.path.join(SRC, "unified_respondents.json")))
idx = {r["submission_id"]: i for i, r in enumerate(respondents)}

# GOP rankings -> parallel arrays
gop_candidates = []
gop_idx = {}
gop = [[] for _ in respondents]
with open(os.path.join(SRC, "unified_gop_rankings.csv"), encoding="utf-8") as f:
    for row in csv.DictReader(f):
        c = row["candidate"]
        if c not in gop_idx:
            gop_idx[c] = len(gop_candidates)
            gop_candidates.append(c)
        i = idx.get(row["submission_id"])
        if i is not None:
            gop[i].append([gop_idx[c], int(row["rank"]), int(row["in_current_field"])])
for lst in gop:
    lst.sort(key=lambda x: x[1])

dem_candidates = []
dem_idx = {}
dem = [[] for _ in respondents]
with open(os.path.join(SRC, "unified_dem_rankings.csv"), encoding="utf-8") as f:
    for row in csv.DictReader(f):
        c = row["candidate"]
        if c not in dem_idx:
            dem_idx[c] = len(dem_candidates)
            dem_candidates.append(c)
        i = idx.get(row["submission_id"])
        if i is not None:
            dem[i].append([dem_idx[c], int(row["rank"])])
for lst in dem:
    lst.sort(key=lambda x: x[1])

with open(os.path.join(DST, "respondents.json"), "w") as f:
    json.dump(respondents, f, separators=(",", ":"))
with open(os.path.join(DST, "gop_rankings.json"), "w") as f:
    json.dump({"candidates": gop_candidates, "rankings": gop}, f, separators=(",", ":"))
with open(os.path.join(DST, "dem_rankings.json"), "w") as f:
    json.dump({"candidates": dem_candidates, "rankings": dem}, f, separators=(",", ":"))

polls = {}
for r in respondents:
    p = polls.setdefault(r["poll_source"], {"n": 0, "min_date": r["submission_date"], "max_date": r["submission_date"]})
    p["n"] += 1
    p["min_date"] = min(p["min_date"], r["submission_date"])
    p["max_date"] = max(p["max_date"], r["submission_date"])
meta = {
    "generated": "2026-11-20",
    "n_respondents": len(respondents),
    "polls": polls,
    "gop_candidates": gop_candidates,
    "dem_candidates": dem_candidates,
    "tribes": ["Faith & Flag Social Conservative", "Traditional / Pro-Business Conservative",
               "America First Populist", "National Security Hawk",
               "Pragmatic / Results-Oriented", "Libertarian-Leaning",
               "Order & Opportunity Center-Left", "Mainstream Liberal",
               "Economic Populist Left", "Progressive / Social Democratic Left",
               "Not sure / Low-signal", "Unclassified / Insufficient data"],
    "model": "Tribe scores: 90% policy priorities + 9% ideology + 1% election signal (Aug only), "
             "renormalized over components present. Feb/Apr priorities were unranked sets (equal weights); "
             "Aug priorities were ranked. Feb ideology 1-5 rescaled to 1-7 (1->1, 2->2, 3->4, 4->6, 5->7). "
             "Candidate rankings are never used for tribe classification.",
}
with open(os.path.join(DST, "meta.json"), "w") as f:
    json.dump(meta, f, indent=1)
print("wrote dashboard data:")
for fn in ["respondents.json", "gop_rankings.json", "dem_rankings.json", "meta.json"]:
    print(f"  {fn}: {os.path.getsize(os.path.join(DST, fn)):,} bytes")
print(f"GOP candidates ({len(gop_candidates)}): {gop_candidates}")
print(f"DEM candidates ({len(dem_candidates)}): {dem_candidates}")
