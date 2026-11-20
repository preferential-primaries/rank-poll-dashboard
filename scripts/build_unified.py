#!/usr/bin/env python3
"""Build the unified RCV polling dataset from the 3 historical JotForm polls.

Sources (fresh JotForm exports WITH Submission ID, Nov 20, 2026):
  Feb2026 - pres_candidate_2026-11-20_with_ids.csv (1,093 rows, incl. Sep 25 straggler)
  Apr2026 - texas_senate_2026-11-20_with_ids.csv (327 rows)
  Aug2026 - pres_nomination_2026-11-20.csv (19 rows)

Tribe model: the live presidential calculateTribes_ model, applied UNIFORMLY
to all three polls (this is the "updated expanded recoding" — the old
Respondents table used a different historical approximation for Feb/Apr, so
scores will shift somewhat vs that table; see validation report):
  - 90% ranked policy priorities (POLICY_AFFINITY vectors)
  -  9% ideology fit (max(0, 1 - |ideo - center| / 3))
  -  1% election signal (top-3 concerns, 50/30/20; Aug only)
  - missing components omitted, remaining weights renormalized
  - Feb/Apr picks are UNRANKED sets -> equal weights (1.00 each); Aug picks
    are ranked -> weights [1.00, 0.80, 0.65, 0.52, 0.42] at original rank
    positions (positions preserved when "Not sure" is skipped)
  - no substantive policy pick -> blank scores; primary "Not sure / Low-signal"
    if "Not sure" was picked, else "Unclassified / Insufficient data"
  - ties broken alphabetically by tribe display name; scores rounded half-up
    to 2 decimals (matching Apps Script Math.round)

Outputs (~/workspace/rcv-polling/unified/):
  unified_respondents.json / .csv - one row per respondent (1,439)
  unified_gop_rankings.csv        - long GOP rankings (all candidates kept;
                                    in_current_field flags the 5 obsolete Feb names;
                                    top3 = 1 when the candidate was ranked 1-3)
  unified_dem_rankings.csv        - long DEM rankings (Aug only; also has top3)
  candidate_availability.json     - which candidates each poll offered
  unified_election_items.csv      - Aug ranked concerns + TX selected statements
  validation_report.json          - comparison vs the old Respondents table
"""
import csv
import json
import math
import os
import re
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Raw JotForm exports live in a LOCAL raw/ folder (gitignored — they contain
# respondent IPs and must never be committed). Override with RCV_RAW_DIR.
FRESH = os.environ.get("RCV_RAW_DIR", os.path.join(REPO, "raw"))
OUT = os.path.join(REPO, "data")

TRIBES = ["Faith & Flag Social Conservative", "Traditional / Pro-Business Conservative",
          "America First Populist", "National Security Hawk",
          "Pragmatic / Results-Oriented", "Libertarian-Leaning",
          "Order & Opportunity Center-Left", "Mainstream Liberal",
          "Economic Populist Left", "Progressive / Social Democratic Left"]
# order: [Faith, Traditional, America First, Hawk, Pragmatic, Libertarian,
#         Order & Opportunity, Mainstream Liberal, Econ Populist Left, Progressive Left]
POLICY_AFFINITY = {
    "limited_gov":    [.55, .90, .35, .35, .45, 1.00, .25, .15, .10, .05],
    "fiscal":         [.35, 1.00, .25, .30, .55, .85, .35, .20, .20, .05],
    "progrowth":      [.30, 1.00, .35, .45, .75, .65, .70, .60, .35, .10],
    "social":         [1.00, .35, .35, .20, .20, .05, .35, .10, .25, 0],
    "borders":        [.60, .40, 1.00, .65, .35, .20, .70, .20, .45, .05],
    "defense":        [.60, .50, .45, 1.00, .45, .10, .65, .40, .35, .10],
    "america1st":     [.45, .15, 1.00, .40, .20, .10, .25, .05, .35, .05],
    "accountability": [.30, .30, .70, .35, .85, .45, .65, .60, .90, .50],
    "pragmatic":      [.20, .50, .20, .30, 1.00, .30, .90, .80, .45, .30],
    "libertarian":    [.05, .35, .10, .10, .40, 1.00, .25, .35, .20, .20],
    "prog_fairness":  [0, .05, .10, .05, .45, .15, .55, .85, .75, 1.00],
    "schools":        [.10, .10, .15, .05, .55, .05, .80, .85, .85, .90],
    "tax_rich":       [0, 0, .20, 0, .30, 0, .55, .70, 1.00, .95],
    "medicare":       [0, 0, .10, 0, .25, 0, .55, .70, .95, 1.00],
}
POLICY_TEXT_TO_KEY = {
    "Limited government & the Constitution": "limited_gov",
    "Fiscal restraint (spending/debt)": "fiscal",
    "Pro-growth economy (jobs, deregulation)": "progrowth",
    "Social & family values": "social",
    "Secure borders & immigration enforcement": "borders",
    "Strong national defense": "defense",
    "America First / populist reform": "america1st",
    "Government accountability & anti-corruption": "accountability",
    "Pragmatic problem-solving (results-oriented)": "pragmatic",
    "Libertarian-leaning (civil liberties, limited regulation)": "libertarian",
    "Progressive reforms for more fairness or equality": "prog_fairness",
    "More government funding of public schools": "schools",
    "Higher taxes on the wealthy": "tax_rich",
    "Universal healthcare like Medicare for all": "medicare",
}
IDEOLOGY_CENTERS = [6.5, 5.8, 6.1, 5.7, 4.2, 5.1, 3.8, 2.7, 3.2, 1.6]
RANK_WEIGHTS = [1.00, 0.80, 0.65, 0.52, 0.42]
ELECTION_WEIGHTS = [0.50, 0.30, 0.20]
FEB_RESCALE = {"1": 1, "2": 2, "3": 4, "4": 6, "5": 7}
IDEOLOGY_LABELS = {1: "Very Liberal", 2: "Liberal", 3: "Somewhat Liberal",
                   4: "Moderate", 5: "Somewhat Conservative", 6: "Conservative",
                   7: "Very Conservative"}
CURRENT_GOP_FIELD = {"Marco Rubio", "Glenn Youngkin", "JD Vance", "Ted Cruz",
                     "Ron DeSantis", "Josh Hawley", "Donald Trump Jr.",
                     "Tucker Carlson", "Other"}

# From the Apps Script source, Code.gs lines 327-390 (verbatim, Nov 20, 2026).
# Keys are the Aug election-concern labels; vectors follow TRIBES order.
ELECTION_AFFINITY = {
    "Preventing Non-Citizen Voting": [.45, .30, .75, .40, .45, .10, .70, .25, .45, .15],
    "Requiring Voter ID": [.45, .40, .65, .35, .55, .10, .80, .35, .55, .20],
    "Requiring Audits": [.25, .45, .40, .35, .85, .20, .75, .70, .65, .55],
    "Requiring Paper Ballots": [.30, .35, .45, .30, .80, .20, .75, .65, .65, .55],
    "Eliminating Vote By Mail": [.35, .25, .65, .30, .25, .05, .45, .10, .30, .05],
    "Enforcing List Maintenance": [.30, .45, .55, .35, .80, .15, .80, .60, .70, .45],
    "Ensuring Timely Reporting of Results": [.20, .45, .35, .30, 1.00, .20, .85, .80, .75, .65],
    "Banning Ranked Choice Voting": [.25, .20, .40, .20, .25, .05, .35, .10, .20, .05],
    "Other": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
}


def round2(x):
    return math.floor(x * 100 + 0.5) / 100


def parse_ranked(cell):
    """'1: Item\\n2: Item' or '1. Item\\n2. Item' -> [(rank, item), ...] sorted by rank."""
    out = []
    for line in (cell or "").replace("\r", "\n").split("\n"):
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(\d+)\s*[:.]\s*(.*)$", line)
        if m:
            out.append((int(m.group(1)), m.group(2).strip()))
        else:
            out.append((len(out) + 1, line))
    return sorted(out)


def parse_multiselect(cell):
    return [x.strip() for x in (cell or "").replace("\r", "\n").split("\n") if x.strip()]


def parse_state(cell):
    m = re.search(r"\(([A-Z]{2})\)", cell or "")
    return m.group(1) if m else (cell or "").strip()


def parse_date(cell):
    cell = (cell or "").strip()
    if not cell:
        return ""
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(cell, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return cell


def tribe_scores(policy_ranked, ideology_7, election_top3):
    """policy_ranked: [(rank, policy_key)] substantive only (Not sure removed).
    ideology_7: int 1-7 or None. election_top3: [concern, ...] up to 3 or None.
    Returns (scores list of 10 round2 numbers or None, primary, runner_up, margin)."""
    if not policy_ranked:
        return None, None, None, None
    # Policy component: weighted mean of affinity vectors.
    wsum = 0.0
    pol = [0.0] * 10
    for rank, key in policy_ranked:
        w = RANK_WEIGHTS[rank - 1] if rank <= len(RANK_WEIGHTS) else RANK_WEIGHTS[-1]
        vec = POLICY_AFFINITY[key]
        for i in range(10):
            pol[i] += w * vec[i]
        wsum += w
    pol = [p / wsum for p in pol]
    components = [(0.90, pol)]
    if ideology_7 is not None:
        ideo = [max(0.0, 1.0 - abs(ideology_7 - c) / 3.0) for c in IDEOLOGY_CENTERS]
        components.append((0.09, ideo))
    if election_top3 and ELECTION_AFFINITY:
        # Faithful to calculateTribes_: weights .50/.30/.20 by top-3 POSITION;
        # unknown issues and all-zero vectors ("Other") are skipped WITHOUT
        # renormalizing (a skipped rank-1 leaves weights summing to 0.50);
        # the component only counts if at least one non-zero vector is present.
        el = [0.0] * 10
        has_signal = False
        for j, concern in enumerate(election_top3[:3]):
            vec = ELECTION_AFFINITY.get(concern)
            if vec is None:
                continue
            if not any(v != 0 for v in vec):
                continue
            has_signal = True
            w = ELECTION_WEIGHTS[j]
            for i in range(10):
                el[i] += w * vec[i]
        if has_signal:
            components.append((0.01, el))
    total_w = sum(w for w, _ in components)
    scores = []
    for i in range(10):
        v = sum(w * vec[i] for w, vec in components) / total_w
        scores.append(round2(100 * v))
    order = sorted(range(10), key=lambda i: (-scores[i], TRIBES[i]))
    primary = TRIBES[order[0]]
    runner = TRIBES[order[1]]
    margin = round2(scores[order[0]] - scores[order[1]])
    return scores, primary, runner, margin


def code_respondent(poll, row):
    """Build one unified respondent record + ranking/election rows from a raw CSV row."""
    sub_id = (row.get("Submission ID") or "").strip()
    date = parse_date(row.get("Submission Date"))
    state = parse_state(row.get("In which US state are you registered to vote?"))
    gender = (row.get("Gender") or "").strip()
    age = (row.get("Age") or "").strip()
    ideo_raw = (row.get("Which best describes your political views?") or "").strip()
    if poll == "Feb2026":
        ideo7 = FEB_RESCALE.get(ideo_raw)
    else:
        try:
            ideo7 = int(ideo_raw) if ideo_raw else None
        except ValueError:
            ideo7 = None
    ideo_norm = round2((ideo7 - 1) / 6) if ideo7 is not None else None
    ideo_label = IDEOLOGY_LABELS.get(ideo7, "") if ideo7 is not None else ""

    # Policy picks
    pol_col = [c for c in row.keys() if "priorities as a" in c or "policy priorities as a voter" in c]
    pol_cell = row.get(pol_col[0], "") if pol_col else ""
    ranked = poll == "Aug2026"
    picks = []
    picked_not_sure = False
    if ranked:
        for rank, item in parse_ranked(pol_cell):
            if item == "Not sure":
                picked_not_sure = True
                continue
            key = POLICY_TEXT_TO_KEY.get(item)
            if key:
                picks.append((rank, key))
    else:
        for pos, item in enumerate(parse_multiselect(pol_cell), start=1):
            if item == "Not sure":
                picked_not_sure = True
                continue
            key = POLICY_TEXT_TO_KEY.get(item)
            if key:
                picks.append((1, key))  # unranked: equal weights (all rank 1)
    # equal weights for unranked: override rank weights by using rank 1 for all
    # (tribe_scores applies RANK_WEIGHTS[0] = 1.00 to each)

    # Election signal (Aug only)
    election_top3 = None
    election_rows = []
    if poll == "Aug2026":
        ecol = [c for c in row.keys() if "Election Integrity Concern" in c][0]
        ranked_concerns = parse_ranked(row.get(ecol, ""))
        election_top3 = [item for _, item in ranked_concerns[:3]]
        for rank, item in ranked_concerns:
            election_rows.append({"submission_id": sub_id, "poll_source": poll,
                                  "item": item, "rank": rank, "selected": 1,
                                  "question": "election_concerns_ranked"})
    if poll == "Apr2026":
        ecol = [c for c in row.keys() if "election reform" in c][0]
        for item in parse_multiselect(row.get(ecol, "")):
            election_rows.append({"submission_id": sub_id, "poll_source": poll,
                                  "item": item, "rank": None, "selected": 1,
                                  "question": "election_statements_multiselect"})

    scores, primary, runner, margin = tribe_scores(picks, ideo7, election_top3)
    if scores is None:
        primary = "Not sure / Low-signal" if picked_not_sure else "Unclassified / Insufficient data"

    # GOP rankings (drop "NaN" phantom entries — one TX ballot has a JotForm
    # drag-rank glitch leaving slot 2 empty — and compress ranks to 1..n)
    gop_col = [c for c in row.keys() if "Republican Presidential Nomination" in c or "2028 GOP nominee" in c][0]
    gop_ranked = [(r, c) for r, c in parse_ranked(row.get(gop_col, "")) if c.strip().lower() != "nan"]
    gop_ranked = [(i + 1, c) for i, (_, c) in enumerate(gop_ranked)]
    gop_rows = [{"submission_id": sub_id, "poll_source": poll, "candidate": cand,
                 "rank": rank, "in_current_field": 1 if cand in CURRENT_GOP_FIELD else 0,
                 "top3": 1 if rank <= 3 else 0}
                for rank, cand in gop_ranked]
    gop_first = gop_ranked[0][1] if gop_ranked else ""
    gop_top3 = [cand for _, cand in gop_ranked[:3]]

    # DEM rankings (Aug only)
    dem_rows = []
    dem_first = ""
    dem_top3 = []
    if poll == "Aug2026":
        dcol = [c for c in row.keys() if "GREATEST chance" in c][0]
        dem_ranked = [(r, c) for r, c in parse_ranked(row.get(dcol, "")) if c.strip().lower() != "nan"]
        dem_ranked = [(i + 1, c) for i, (_, c) in enumerate(dem_ranked)]
        dem_rows = [{"submission_id": sub_id, "poll_source": poll, "candidate": cand, "rank": rank,
                     "top3": 1 if rank <= 3 else 0}
                    for rank, cand in dem_ranked]
        dem_first = dem_ranked[0][1] if dem_ranked else ""
        dem_top3 = [cand for _, cand in dem_ranked[:3]]

    rec = {
        "submission_id": sub_id, "poll_source": poll, "submission_date": date,
        "state": state, "gender": gender, "age": age,
        "ideology_1_7": ideo7, "ideology_norm": ideo_norm,
        "ideology_raw": ideo_raw, "ideology_label": ideo_label,
        "policy_picks": [k for _, k in picks],
        "n_policy_picks": len(picks),
        "picked_not_sure": 1 if picked_not_sure else 0,
        "tribe_scores": scores,
        "primary_tribe": primary, "runner_up_tribe": runner or "",
        "tribe_margin": margin,
        "gop_first_choice": gop_first, "gop_n_ranked": len(gop_ranked),
        "gop_top3": gop_top3,
        "dem_first_choice": dem_first, "dem_top3": dem_top3,
        "election_top_concern": election_top3[0] if election_top3 else "",
    }
    # Poll-specific fields
    if poll == "Feb2026":
        tcol = [c for c in row.keys() if "tariff policies" in c][0]
        ecol2 = [c for c in row.keys() if "eminent domain" in c][0]
        rec["tariff_support"] = (row.get(tcol) or "").strip()
        rec["eminent_domain_ban"] = (row.get(ecol2) or "").strip()
    if poll == "Apr2026":
        scol = [c for c in row.keys() if "Texas Republican US Senate" in c][0]
        icol = [c for c in row.keys() if "military force against Iran" in c][0]
        tcol = [c for c in row.keys() if "feel about President Trump's tariff" in c][0]
        pcol = [c for c in row.keys() if "Political party" in c][0]
        tariff_ranked = parse_ranked(row.get(tcol, ""))
        rec["senate_choice"] = (row.get(scol) or "").strip()
        rec["iran_force"] = (row.get(icol) or "").strip()
        rec["tariff_top"] = tariff_ranked[0][1] if tariff_ranked else ""
        rec["party"] = (row.get(pcol) or "").strip()
    return rec, gop_rows, dem_rows, election_rows


def load_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    sources = [
        ("Feb2026", os.path.join(FRESH, "pres_candidate_2026-11-20_with_ids.csv")),
        ("Apr2026", os.path.join(FRESH, "texas_senate_2026-11-20_with_ids.csv")),
        ("Aug2026", os.path.join(FRESH, "pres_nomination_2026-11-20.csv")),
    ]
    respondents, gop_rows, dem_rows, elec_rows = [], [], [], []
    for poll, path in sources:
        for row in load_csv(path):
            rec, g, d, e = code_respondent(poll, row)
            respondents.append(rec)
            gop_rows.extend(g)
            dem_rows.extend(d)
            elec_rows.extend(e)
    print(f"respondents: {len(respondents)}")
    print(f"GOP ranking rows: {len(gop_rows)} | DEM rows: {len(dem_rows)} | election rows: {len(elec_rows)}")
    import collections
    print("by poll:", dict(collections.Counter(r["poll_source"] for r in respondents)))
    print("primary tribe:", dict(collections.Counter(r["primary_tribe"] for r in respondents)))

    json.dump(respondents, open(os.path.join(OUT, "unified_respondents.json"), "w"), indent=1)

    # CSV: flatten tribe scores into 10 columns
    fields = ["submission_id", "poll_source", "submission_date", "state", "gender", "age",
              "ideology_1_7", "ideology_norm", "ideology_raw", "ideology_label", "policy_picks", "n_policy_picks",
              "picked_not_sure"] + [f"affinity_{t}" for t in
              ["faith_flag", "traditional", "america_first", "hawk", "pragmatic", "libertarian",
               "order_opportunity", "mainstream_liberal", "econ_populist_left", "progressive_left"]] + \
             ["primary_tribe", "runner_up_tribe", "tribe_margin", "gop_first_choice", "gop_n_ranked",
              "gop_top3", "dem_first_choice", "dem_top3", "election_top_concern",
              "tariff_support", "eminent_domain_ban",
              "senate_choice", "iran_force", "tariff_top", "party"]
    with open(os.path.join(OUT, "unified_respondents.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in respondents:
            flat = dict(r)
            flat["policy_picks"] = "|".join(r["policy_picks"])
            flat["gop_top3"] = "|".join(r["gop_top3"])
            flat["dem_top3"] = "|".join(r["dem_top3"])
            for i, t in enumerate(["faith_flag", "traditional", "america_first", "hawk", "pragmatic",
                                   "libertarian", "order_opportunity", "mainstream_liberal",
                                   "econ_populist_left", "progressive_left"]):
                flat[f"affinity_{t}"] = r["tribe_scores"][i] if r["tribe_scores"] else ""
            del flat["tribe_scores"]
            w.writerow(flat)
    for name, rows, fn in [("unified_gop_rankings.csv", gop_rows, ["submission_id", "poll_source", "candidate", "rank", "in_current_field", "top3"]),
                           ("unified_dem_rankings.csv", dem_rows, ["submission_id", "poll_source", "candidate", "rank", "top3"]),
                           ("unified_election_items.csv", elec_rows, ["submission_id", "poll_source", "item", "rank", "selected", "question"])]:
        with open(os.path.join(OUT, name), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fn, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    # Candidate availability: which candidates each poll offered (drives the
    # dashboard's dynamic denominators — a candidate's % is measured only
    # over respondents in polls where that candidate was on the ballot).
    availability = {"gop": {}, "dem": {}}
    for rows, kind in [(gop_rows, "gop"), (dem_rows, "dem")]:
        by_poll = collections.defaultdict(list)
        for row in rows:
            if row["candidate"] not in by_poll[row["poll_source"]]:
                by_poll[row["poll_source"]].append(row["candidate"])
        availability[kind] = dict(sorted(by_poll.items()))
    json.dump(availability, open(os.path.join(OUT, "candidate_availability.json"), "w"), indent=1)
    print("candidate availability:", {k: {p: len(v) for p, v in d.items()} for k, d in availability.items()})
    print("wrote unified files to", OUT)
    if ELECTION_AFFINITY is None:
        print("NOTE: ELECTION_AFFINITY not set — Aug scores omit the 1% election component (provisional, within ~1pt).")


if __name__ == "__main__":
    main()
