"""Reduce one run directory to the numbers a comparison needs, into summary.json.

    .venv/bin/python -B tools/summarise_run.py overnight/runs/<stamp>_<label>
    .venv/bin/python -B tools/summarise_run.py --compare        # every run, side by side

Everything here is parsed from the run's own cycle.log and events.jsonl, so a summary
cannot describe a build other than the one run.json records.
"""
import json, os, re, statistics as st, sys

def summarise(run):
    log = os.path.join(run, "cycle.log")
    rows = open(log).read().splitlines() if os.path.exists(log) else []
    rel = [float(m[1]) for l in rows if (m := re.search(r"\[deal\] replacement card seen; released ([\d.]+)s", l))]
    tout = sum(1 for l in rows if "no replacement card seen in" in l)
    ep = [float(m[1]) for l in rows if (m := re.search(r"\[reveal\] episode t_first=\+([\d.]+)s", l))]
    peaks = [float(m[1]) for l in rows if (m := re.search(r"episode t_first=\+[\d.]+s after the play, peak ([\d.]+)", l))]
    noep = sum(1 for l in rows if "no episode within" in l)
    mis = sum(1 for l in rows if "intended card absent" in l) + sum(1 for l in rows if "no OPPONENT card" in l)
    plays = sum(1 for l in rows if "Decision: Playing" in l)
    disc = sum(1 for l in rows if "discarding the weakest" in l)
    wins = sum(1 for l in rows if "WIN #" in l); loss = sum(1 for l in rows if "LOSS #" in l)
    api = 0
    for l in rows:
        m = re.search(r"\[api\] (\d+)/", l)
        if m: api = max(api, int(m[1]))
    midd = sum(1 for l in rows if "mid-deal or partial" in l)
    local0 = sum(1 for l in rows if re.search(r"local found [0-4] cards", l))
    # turn length from the event log's confirm_play presses
    evp = os.path.join(run, "events.jsonl"); turns = []
    if os.path.exists(evp):
        ts = [json.loads(l)["t"] for l in open(evp)
              if '"confirm_play"' in l and '"press"' in l]
        turns = [b - a for a, b in zip(ts, ts[1:]) if 5 < b - a < 200]
    walked = next((m[1] for l in rows if (m := re.search(r"arrived on walk (\d+) of", l))), None)
    span = None
    if rows:
        try: span = (float(rows[-1].split()[0]) - float(rows[0].split()[0])) / 60.0
        except Exception: pass
    s = {
        "run": os.path.basename(run),
        "build": json.load(open(os.path.join(run, "run.json"))) if os.path.exists(os.path.join(run, "run.json")) else {},
        "minutes": round(span, 1) if span else None,
        "walk_arrived_on_attempt": walked,
        "matches": {"won": wins, "lost": loss},
        "turns": {"plays": plays, "discard_decisions": disc,
                  "length_p50": round(st.median(turns), 1) if turns else None,
                  "length_n": len(turns)},
        "deal": {"fired": len(rel), "timed_out": tout,
                 "released_p50": round(st.median(rel), 1) if rel else None,
                 "released_max": max(rel) if rel else None,
                 "seconds_lost_to_timeouts": round(tout * (json.load(open(os.path.join(run, "run.json")))["constants"]["POST_PLAY_DEAL_MAX_WAIT"] if os.path.exists(os.path.join(run, "run.json")) else 35), 1)},
        "reveal": {"episodes_found": len(ep), "none_found": noep,
                   "peak_read_p50": round(st.median(peaks), 3) if peaks else None,
                   "misreads": mis},
        "reads": {"api_calls": api, "mid_deal_retries": midd, "local_hand_short": local0},
    }
    json.dump(s, open(os.path.join(run, "summary.json"), "w"), indent=1)
    return s

def show(s):
    b = s.get("build", {}).get("constants", {})
    print(f"\n=== {s['run']}   build {s.get('build',{}).get('git_sha','?')}"
          f"{'  DIRTY' if s.get('build',{}).get('tree_dirty') else ''}")
    print(f"  deal threshold {b.get('HAND_DEAL_THRESHOLD')}  cap {b.get('POST_PLAY_DEAL_MAX_WAIT')}"
          f"  peak settle {b.get('PEAK_SETTLE_SEC')}")
    print(f"  {s['minutes']} min, walk arrived on attempt {s['walk_arrived_on_attempt']},"
          f" {s['matches']['won']}W/{s['matches']['lost']}L, {s['reads']['api_calls']} paid calls")
    d = s["deal"]; r = s["reveal"]; t = s["turns"]
    print(f"  turn p50 {t['length_p50']}s (n={t['length_n']}), {t['plays']} plays")
    print(f"  deal: fired {d['fired']}, timed out {d['timed_out']} "
          f"({d['seconds_lost_to_timeouts']}s lost), released p50 {d['released_p50']}s max {d['released_max']}s")
    print(f"  reveal: found {r['episodes_found']}, none {r['none_found']}, "
          f"peak read p50 {r['peak_read_p50']}, misreads {r['misreads']}")
    print(f"  reads: {s['reads']['mid_deal_retries']} mid-deal retries, "
          f"{s['reads']['local_hand_short']} short local hands")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--compare":
        base = "overnight/runs"
        for d in sorted(os.listdir(base)):
            p = os.path.join(base, d)
            if os.path.isdir(p) and os.path.exists(os.path.join(p, "cycle.log")):
                try: show(summarise(p))
                except Exception as e: print(f"\n=== {d}: could not summarise ({e})")
    else:
        show(summarise(sys.argv[1]))
