"""Build the run dashboard: state JSON (for the artifact database) + the page HTML.

    .venv/bin/python -B tools/dashboard.py
      -> overnight/dashboard_state.json           write_db this after every trial
      -> <scratchpad>/auto_baseball_dashboard.html  publish once; re-publish only on layout changes

State comes from the run's own files (overnight/ab_goal_leg.json, .log, the
pre-sweep frames re-scored with mask + OCR) plus the queue below, which is the
plan as agreed with the user. Read-only over run files.
"""
import json
import os
import re
import subprocess
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
STATE = os.path.join(ROOT, "overnight", "dashboard_state.json")
HTML = os.environ.get("DASH_HTML", os.path.join(
    "/private/tmp/claude-502/-Users-bpatterson-Documents-Claude-Cowork-Personal-Auto-Baseball/e6392fcc-4b59-4ace-b5b6-76c4bf041181/scratchpad",
    "auto_baseball_dashboard.html"))

QUEUE = [
    {"title": "THE 25, fifteenth launch: the same build again", "state": "running",
     "detail": "Fourteenth launch 22 of 25 at a walk median of 82 s. Its three failures were three different spots (a coat rack in the shop, the window past the dealer, the stairs alcove); the rewind rule fired once and behaved as built. Readers and censuses found no rule worth building on one to three trials, so the build runs again while the '$50' census finishes for the detector."},
    {"title": "THE 25, fourteenth launch: the rewind rule", "state": "done",
     "detail": "Thirteenth launch 23 of 25 at a walk median of 84 s: the 24 of 25 repeats on the same build. Its two failures were a detector miss with the prompt on screen and the third identical loss at the bar-tables stop. Landed now: a thin fit at a stop counts as nothing, a retry needs credible evidence of being short, and a stop that cannot be verified rewinds to the last credible position and re-approaches instead of being accepted on faith. A census over every route frame for the '$50' token is running for the detector."},
    {"title": "THE 25, thirteenth launch: the same build again", "state": "done",
     "detail": "Twelfth launch 24 of 25, walk median 86 s against 105 s the batch before, best streak 21. The one failure was the doorway pillar at the bar entrance followed by a stop accepted unverified; the rewind rule for that is in its final check and lands at this batch's end. This run measures whether 24 of 25 repeats on the same build."},
    {"title": "THE 25, twelfth launch: tie fix, tail gate, detector rule", "state": "done",
     "detail": "Eleventh launch 21 of 25. Landed now: a stop is a tie only when the runner-up is a different place (the old rule fired on 28 of 37 replayed stops and cost two thirds of the extra time per arrival), the look-around stops at the first strong look, the prompt check is only consulted in the last 30 waypoints, and the detector believes a 0.20 correlation when it also reads a prompt word (measured on all 7,885 route frames: zero false positives). The rewind-on-unverified rule is in build for the next boundary."},
    {"title": "THE 25, eleventh launch: end-turn rule in, dark-frame retry out", "state": "done",
     "detail": "The tenth launch made 11 true arrivals in a row, then trial 12 'arrived' on the street: the new dark-frame retry of the prompt detector fired on the office doorway facing the L&B storefront. Reverted at once (that detector is the $50 gate; a 500-frame check had said zero false positives and the 701st frame fired). Landed instead: past the last turn stop, a large offset turns the camera toward the dealer instead of strafing, built by a builder and three skeptics. The tie fix is next."},
    {"title": "THE 25, tenth launch: retry gate + dark-frame detector", "state": "done",
     "detail": "The pan A/B finished 9/10 against 8/10, no difference, flag stays off. Tonight's readers and three studies (fast vs slow, the record 67.9 s run, the cost of each rule) agree: collisions are flat, the extra 20-30 s per arrival is ceremony at the turn stops, and two thirds of it is the tie rule firing on near-duplicate waypoints. Landed now: no retry pushes after a wall-scale fit (the slow runs' 30-45 s at stops 88 and 129), and the prompt detector retries dark frames (trial 10 stood at the prompt for three iterations unseen). Next boundary: turn toward the dealer at the end, and the tie fix."},
    {"title": "Pan A/B, second attempt, on the ladder round", "state": "done",
     "detail": "First attempt stopped at 4 trials: Wanda Fuller stood on the route in the portrait room and three trials in a row walked into her face, both arms. Readers on every failed trial tonight: 5 of 7 were an NPC filling the view, and each died having tried one or two escape rungs because the lost budget ran out before the ladder finished. Now every blockage gets the whole ladder, a sidestep is a 0.6 s detour held for three targets, and the pan A/B runs again on top, 10 v 10 interleaved."},
    {"title": "Pan A/B, first attempt", "state": "done",
     "detail": "The ninth launch of the 25 went 1 of 5: three trials lost right after the bar-tables stop, where the head-on check has failed in 8 of the last 9 trials and the sideways look's arithmetic disagreed with the next reading by 300 px. The judge's first item was to A/B the pan that matches each look against its own recorded frame. Off arm = the 25's own configuration, so nothing is lost by switching. Readers are on every failed trial."},
    {"title": "THE 25, ninth launch (80182ac)", "state": "done",
     "detail": "Eighth launch 2/2 (155 s, 104 s), seventh 1/2. New in this one: the look-around strafe is one ordinary correction (batch 7's failure was a doubled one), four same-side junk fits steer once (0 of 24 arriving trials had four; 5 failing ones did), and the pan-from-run sits behind a flag, off, for its own A/B. Every failed trial gets a screenshot reader the moment it lands; the ninth's trial 1 (lost at k=173, the bar-tables stop again) is being read now."},
    {"title": "THE 25, seventh launch", "state": "done",
     "detail": "Sixth launch went 4 of 7 valid; both bar-entrance losses were the same event, read by two agents from the frames: the loop walked nose-first into the big portrait at the end of the portrait room and had no backward move. Now a blind sensor near a wall gets one push before the stop, a wedged stop steps back before waiting or retrying, and the escape ladder is jump, back, left, right. Every failed trial now gets a screenshot reader the moment it lands."},
    {"title": "Arrival review: did they wander?", "state": "done",
     "detail": "13 arrivals read frame by frame: 12 minor detours, 1 wandered-and-lucky, 0 off the route. Every detour was a wedge at a real obstacle: the exit-door threshold and the bartender's counter with two NPCs and two steins."},
    {"title": "Batches 1-4", "state": "done",
     "detail": "1: 2/4, turned at the door before reaching it (your call). 2 and 3: 0/2 each, lost at the street crossing where the shop facade looks the same from the doorway and halfway across. 4: 8/10. Each failure was one spot and one fix."},
    {"title": "Sensor go/no-go", "state": "done",
     "detail": "GO. Your drive's own held-out frames, loop's own hint: 82% within one waypoint, 96% within two, 4% abstain, tracked to the end. Office drive: 96.7% within one when it answers, 16.6% abstain."},
    {"title": "Build the three modules", "state": "done",
     "detail": "Sensor, recorder, controller, harness: 3 builders + 3 skeptics, 18 agents, every module refuted at least once and fixed; 200 tests across the four files; mutants all caught. Snoopy's coder model reviewed all four: one real gap (heading coverage) in four reviews."},
    {"title": "Record the route chain", "state": "done",
     "detail": "You drove it (116 s, stick logged via pygame, compass on 94% of frames, stopped itself on the prompt). The 61 s idle head was trimmed."},
    {"title": "Fast A/B (a) extend", "state": "done",
     "detail": "KILLED at trial 5 of 20 at your request. Not a result at n=2; --resume can pick it up if dead reckoning ever comes back."},
]
DECISIONS = [
    {"title": "If the trials stall at one spot", "detail": "The journal names the waypoint. Your diagonal camera moves (pitch) are the likely cause there; a re-drive of that stretch takes a minute."},
    {"title": "Ceiling for a closed-loop trial", "detail": "400 s walk cap plus a 180 s setup budget, 580 s external kill; over the cap scores TIMED OUT, as you set for the fast harness."},
]


def executed_legs():
    from goal_leg_sheet import executed_legs as _e
    return _e()


RUNS = [  # (json, log, frames dir, name, arms) -- the newest json on disk is the live panel
    ("ab_fast_trim.json", "ab_fast_trim.log", "ab_fast_trim_frames", "Fast A/B (c): jukebox leg as recorded vs trimmed 0.05u", ("recorded", "trimmed")),
    ("ab_fast_extend.json", "ab_fast_extend.log", "ab_fast_extend_frames", "Fast A/B (a): recorded vs +0.10u", ("recorded", "extended")),
    ("ab_goal_extend.json", "ab_goal_extend.log", "goal_extend_failframes", "Goal-leg extension A/B: recorded vs +0.10u", ("recorded", "extended")),
    ("ab_goal_leg.json", "ab_goal_leg.log", "goal_leg_failframes", "Goal-leg A/B: shipped vs recorded", ("shipped", "recorded")),
]


def newest_run():
    have = [(os.path.getmtime(os.path.join(ROOT, "overnight", r[0])), r) for r in RUNS
            if os.path.exists(os.path.join(ROOT, "overnight", r[0]))]
    return max(have)[1]


def _chain_rows():
    """The closed-loop batch (overnight/chain_trials.json) as one-arm rows."""
    j = json.load(open(os.path.join(ROOT, "overnight", "chain_trials.json")))
    rows, durations = [], []
    for r in j.get("runs", []):
        outcome = (r.get("outcome") or ("ARRIVED" if r.get("arrived") else "FAILED")).lower()
        secs = (r.get("setup_seconds") or 0) + (r.get("seconds") or 0)
        durations.append(secs)
        rows.append({"trial": r.get("trial", len(rows) + 1), "arm": r.get("arm") or "closed-loop", "outcome": outcome,
                     "why": (r.get("failure") or "")[:90],
                     "leg_s": r.get("walk_seconds"), "setup_s": r.get("setup_seconds"),
                     "located": f"k={r.get('k_final')}/{r.get('waypoints')}",
                     "recheck": r.get("at_table_recheck"),
                     "kinds": [f"{r.get('pushes')} pushes, {r.get('iterations')} it"],
                     "prompt_on_screen": None})
    arms = sorted({r["arm"] for r in rows}) or ["closed-loop"]
    tallies = {}
    for arm in arms:
        rs = [r for r in rows if r["arm"] == arm]
        val = [r for r in rs if r["outcome"] != "invalid"]
        arrived = [r["outcome"] == "arrived" for r in val]
        streak = best = 0
        for a in arrived:
            streak = streak + 1 if a else 0
            best = max(best, streak)
        tallies[arm] = {"valid": len(val), "arrived": sum(arrived), "invalid": len(rs) - len(val),
                        "prompt_on_screen": best, "executed": streak}
    total = j.get("trials", 25)
    remaining = total - len(rows)
    med = statistics.median(durations) if durations else 150
    def fmt(s):
        return f"{s/60:.0f} min" if s < 3600 else f"{s/3600:.1f} h"
    eta = f"about {fmt(remaining * med)}" if remaining else "finished"
    name = f"THE 25: closed loop on the user's chain ({j.get('chain', '?')}), {j.get('time_cap')} s cap"
    return rows, tallies, {"total": total, "done": len(rows), "remaining": remaining, "eta": eta,
                           "median_trial_s": round(med), "name": name, "harness": "overnight/chain_trials.py",
                           "arms": arms, "note": "prompt-on-screen column = best streak; executed = current streak"}


def rows_and_tallies():
    import glob
    chain_p = os.path.join(ROOT, "overnight", "chain_trials.json")
    if os.path.exists(chain_p) and os.path.getmtime(chain_p) >= max(
            os.path.getmtime(os.path.join(ROOT, "overnight", r[0])) for r in RUNS
            if os.path.exists(os.path.join(ROOT, "overnight", r[0]))):
        return _chain_rows()
    from PIL import Image
    import table_prompt as tp
    import prompt_ocr_ab as ocr
    import goal_leg_sheet
    jname, lname, fdir, name, arms = newest_run()
    j = json.load(open(os.path.join(ROOT, "overnight", jname)))
    runs = j["runs"]
    goal_leg_sheet.LOG = os.path.join(ROOT, "overnight", lname)
    legs = executed_legs() if os.path.exists(goal_leg_sheet.LOG) else []
    pre = sorted(glob.glob(os.path.join(ROOT, "overnight", fdir, "at_dealer_table_[0-9]*.jpg")))
    # Per-frame scores are CACHED by filename: re-scoring every frame on every
    # update was ~30s of CPU beside a live run (2026-09-07, the user saw the
    # stream go sluggish). A new frame costs ~2s; the rest cost nothing.
    cache_p = os.path.join(ROOT, "overnight", "goal_leg_frame_scores.json")
    try:
        cache = json.load(open(cache_p))
    except Exception:
        cache = {}
    prompt = {}                                   # trial -> prompt on screen at the leg's end
    for k, (t, arm, _o) in enumerate(legs):
        if k < len(pre):
            name = os.path.basename(pre[k])
            if name not in cache:
                im = Image.open(pre[k]).convert("RGB")
                cache[name] = bool(tp.at_table(im)) or ocr.read(im)["words"] >= 2
            prompt[t] = cache[name]
    json.dump(cache, open(cache_p, "w"), indent=1)
    rows, durations = [], []
    for i, r in enumerate(runs, 1):
        arrived = r.get("arrived")
        if arrived is None:
            outcome, secs = "invalid", r.get("seconds") or (r.get("setup_seconds") or 0)
            why = r.get("reason", "unmeasurable")
        else:
            outcome = r.get("outcome") or ("arrived" if arrived else "missed")   # fast harness: timed_out too
            secs = (r.get("setup_seconds") or 0) + (r.get("seconds") or 0)
            why = "" if outcome != "timed_out" else "arrived, but slower than the cap"
        durations.append(secs)
        rows.append({"trial": i, "arm": r["arm"], "outcome": outcome, "why": why,
                     "leg_s": r.get("seconds") if arrived is not None else None,
                     "setup_s": r.get("setup_seconds"),
                     "located": r.get("located"), "recheck": r.get("recheck_at_table"),
                     "kinds": r.get("failure_kinds_leg_end") or [],
                     "prompt_on_screen": prompt.get(i)})
    tallies = {}
    for arm in arms:
        rs = [r for r in rows if r["arm"] == arm]
        val = [r for r in rs if r["outcome"] != "invalid"]
        tallies[arm] = {"valid": len(val), "arrived": sum(r["outcome"] == "arrived" for r in val),
                        "invalid": len(rs) - len(val),
                        "prompt_on_screen": sum(1 for r in rs if r["prompt_on_screen"]),
                        "executed": sum(1 for r in rs if r["prompt_on_screen"] is not None)}
    total = j["trials"] * 2
    remaining = total - len(rows)
    med = statistics.median(durations) if durations else 360
    lo, hi = remaining * min(durations or [90]), remaining * 1200
    def fmt(s):
        return f"{s/60:.0f} min" if s < 3600 else f"{s/3600:.1f} h"
    eta = (f"about {fmt(remaining * med)} (from {fmt(lo)} to {fmt(hi)} if every setup exhausts itself)"
           if remaining else "finished")
    return rows, tallies, {"total": total, "done": len(rows), "remaining": remaining, "eta": eta,
                           "median_trial_s": round(med), "name": name, "harness": jname.replace(".json", ".py"), "arms": list(arms)}


def done_today():
    out = subprocess.run(["git", "log", "--since=2026-09-07 00:00", "--format=%h%x09%s"],
                         capture_output=True, text=True, cwd=ROOT).stdout.strip().splitlines()
    keep = []
    for line in out:
        h, _, s = line.partition("\t")
        if s.startswith(("HANDOFF", "CLAUDE.md:", "Pending after")):
            continue
        keep.append({"hash": h, "title": s[:110]})
    return keep[:12]


REPLIES = os.path.join(ROOT, "overnight", "dashboard_replies.json")


def _replies():
    """[{ts, to, text}] -- the session's answers to inbox messages; edited by hand."""
    try:
        return json.load(open(REPLIES))
    except Exception:
        return []


def build_state():
    rows, tallies, run = rows_and_tallies()
    paused = "--paused" in sys.argv
    queue = [dict(q, state=("paused" if q["state"] == "running" and paused else q["state"])) for q in QUEUE]
    if paused:
        queue[0]["detail"] += " PAUSED at the user's request; resume with `overnight/ab_goal_leg.py --resume`."
    return {
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_epoch": int(time.time()),
        "run": {"paused": paused, **run, "rows": rows, "tallies": tallies},
        "queue": queue, "decisions": DECISIONS, "done": done_today(),
        "replies": _replies(),
        "talk": "Messages land in the board's inbox; the session reads it at every update and answers here. To wake it right now, add a comment on the page and choose Send to Claude.",
    }


PAGE = r'''<title>Auto Baseball Control Room</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;700&family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;600&display=swap">
<style>
:root{--bg:#EEF0F3;--panel:#FFFFFF;--ink:#1B1D21;--mute:#5B6470;--line:#D3D7DD;--accent:#2E6BE6;--accent-ink:#FFFFFF;
--good:#2F8F5B;--bad:#C43D3D;--warn:#C98A1B;--inv:#8A9099;--chip:#E6E9EE;--code:#F3F5F8;color-scheme:light dark}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#15171A;--panel:#1E2126;--ink:#E8EAED;--mute:#9AA3AE;--line:#30353C;--accent:#6E9BFF;--accent-ink:#0F1420;--good:#4FB37A;--bad:#E06060;--warn:#E0A64A;--inv:#8A9099;--chip:#2A2F36;--code:#191C21}}
:root[data-theme="dark"]{--bg:#15171A;--panel:#1E2126;--ink:#E8EAED;--mute:#9AA3AE;--line:#30353C;--accent:#6E9BFF;--accent-ink:#0F1420;--good:#4FB37A;--bad:#E06060;--warn:#E0A64A;--inv:#8A9099;--chip:#2A2F36;--code:#191C21}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font:15px/1.5 "IBM Plex Sans",system-ui,sans-serif;margin:0;padding:24px 20px 56px}
h1,h2,h3{font-family:"Archivo","Arial Narrow",sans-serif;text-wrap:balance;margin:0}
h1{font-size:26px;font-weight:700;letter-spacing:-.01em}
h2{font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--mute)}
.mono,td.n,.chip,.eta b{font-family:"IBM Plex Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums}
.wrap{max-width:1080px;margin:0 auto;display:grid;gap:20px}
.strip{display:flex;flex-wrap:wrap;align-items:center;gap:14px 22px;padding:16px 20px;background:var(--panel);border:1px solid var(--line);border-left:5px solid var(--accent)}
.strip .live{display:inline-flex;align-items:center;gap:8px;font-weight:600}
.dot{width:10px;height:10px;border-radius:50%;background:var(--good);box-shadow:0 0 0 3px color-mix(in srgb,var(--good) 25%,transparent)}
.dot.off{background:var(--inv);box-shadow:none}
.eta{color:var(--mute)}.eta b{color:var(--ink);font-weight:600}
.upd{margin-left:auto;color:var(--mute);font-size:13px}
.grid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:20px}
@media (max-width:820px){.grid{grid-template-columns:1fr}}
section{background:var(--panel);border:1px solid var(--line);padding:18px 20px;display:grid;gap:14px;align-content:start}
.tallies{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.tally{border:1px solid var(--line);padding:12px 14px;display:grid;gap:4px}
.tally .arm{font-weight:600}.tally .big{font-size:28px;line-height:1.1}.tally small{color:var(--mute)}
table{width:100%;border-collapse:collapse;font-size:14px}
th{font-family:"Archivo",sans-serif;text-transform:uppercase;letter-spacing:.06em;font-size:11px;color:var(--mute);text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}
td{padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
td.n{text-align:right;white-space:nowrap}
.tbl{overflow-x:auto}
.chip{display:inline-block;font-size:12px;padding:2px 8px;border-radius:3px;background:var(--chip);color:var(--ink)}
.chip.arrived{background:color-mix(in srgb,var(--good) 18%,transparent);color:var(--good);font-weight:600}
.chip.missed{background:color-mix(in srgb,var(--bad) 16%,transparent);color:var(--bad);font-weight:600}
.chip.invalid{color:var(--inv);border:1px dashed var(--inv);background:transparent}
.chip.timed_out{background:color-mix(in srgb,var(--warn) 18%,transparent);color:var(--warn);font-weight:600}
.chip.arm{background:transparent;border:1px solid var(--line);color:var(--mute)}
.chip.on{background:color-mix(in srgb,var(--accent) 16%,transparent);color:var(--accent);font-weight:600}
ol.q{list-style:none;margin:0;padding:0;display:grid;gap:10px}
ol.q li{display:grid;grid-template-columns:auto 1fr;gap:12px;align-items:start;padding:10px 12px;border:1px solid var(--line)}
ol.q li.running{border-color:var(--accent);box-shadow:inset 4px 0 0 var(--accent)}
ol.q li.done{opacity:.6}
.state{font-family:"IBM Plex Mono",monospace;font-size:11px;text-transform:uppercase;letter-spacing:.06em;padding:3px 7px;border-radius:3px;background:var(--chip);color:var(--mute);white-space:nowrap;margin-top:2px}
li.running .state{background:var(--accent);color:var(--accent-ink)}
li.blocked .state{background:transparent;border:1px dashed var(--inv)}
li.paused .state{background:var(--warn);color:#1B1D21}
ol.q li.paused{border-color:var(--warn);box-shadow:inset 4px 0 0 var(--warn)}
.q b{display:block;font-weight:600}.q p{margin:2px 0 0;color:var(--mute);font-size:14px}
.q .on{color:var(--warn);font-size:13px}
ul.plain{margin:0;padding-left:18px;display:grid;gap:8px}
ul.plain li b{font-weight:600}
ul.done{list-style:none;padding:0;margin:0;display:grid;gap:6px;font-size:14px}
ul.done code{font-family:"IBM Plex Mono",monospace;background:var(--code);padding:1px 5px;border-radius:3px;color:var(--mute)}
.talk{border-left:5px solid var(--accent)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:20px}
@media (max-width:820px){.two{grid-template-columns:1fr}}
.box{display:grid;gap:10px}
textarea,input[type=text]{width:100%;font:inherit;color:var(--ink);background:var(--code);border:1px solid var(--line);border-radius:3px;padding:8px 10px;resize:vertical}
button{font:600 14px "IBM Plex Sans",sans-serif;color:var(--accent-ink);background:var(--accent);border:0;border-radius:3px;padding:8px 14px;cursor:pointer}
button.quiet{background:transparent;color:var(--mute);border:1px solid var(--line)}
button:disabled{opacity:.5;cursor:default}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.answer{white-space:pre-wrap;min-height:1.5em;padding:10px 12px;background:var(--code);border-radius:3px}
.msgs{display:grid;gap:8px}
.msg{padding:8px 12px;border-left:3px solid var(--line)}
.msg.you{border-color:var(--accent)}.msg.me{border-color:var(--good)}
.msg small{display:block;color:var(--mute);font-size:12px}
[hidden]{display:none!important}
.talk p{margin:0}
.note{color:var(--mute);font-size:13px}
kbd{font-family:"IBM Plex Mono",monospace;font-size:12px;border:1px solid var(--line);border-bottom-width:2px;border-radius:3px;padding:0 5px;background:var(--code)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
@media (prefers-reduced-motion:no-preference){.dot:not(.off){animation:pulse 2s ease-in-out infinite}}
@keyframes pulse{50%{box-shadow:0 0 0 6px color-mix(in srgb,var(--good) 10%,transparent)}}
</style>
<div class="wrap">
  <div class="strip" id="strip"></div>
  <div class="grid">
    <section>
      <h2>Live run</h2>
      <h1 id="runname"></h1>
      <div class="tallies" id="tallies"></div>
      <div class="tbl"><table id="rows"></table></div>
      <p class="note">INVALID is not a failure: the setup never reached the start node, or the stream died. TIMED OUT is a failure: a leg over 60s or a trial over 400s, counted against the arm. "Prompt on screen" is the pre-sweep frame re-read with the mask plus OCR.</p>
    </section>
    <div style="display:grid;gap:20px;align-content:start">
      <section><h2>Queue</h2><ol class="q" id="queue"></ol></section>
      <section><h2>Your decisions</h2><ul class="plain" id="decisions"></ul></section>
    </div>
  </div>
  <div class="two">
    <section class="talk box" id="askbox" hidden>
      <h2>Ask the board</h2>
      <p class="note">A fresh Claude that sees only this board's data — instant answers about what is running and what is next. It is not the live session.</p>
      <div class="answer" id="answer">Ask something like "why is trial 5 invalid?"</div>
      <div class="row"><input type="text" id="q" placeholder="Your question" aria-label="Question for the board"><button id="ask">Ask</button><button class="quiet" id="stop" hidden>Stop</button></div>
      <p class="note" id="asknote"></p>
    </section>
    <section class="talk box">
      <h2>Message the session</h2>
      <p class="note" id="talk"></p>
      <div class="msgs" id="msgs"></div>
      <div class="row"><textarea id="m" rows="2" placeholder="Anything for the session: an instruction, a question, a change of plan." aria-label="Message to the session"></textarea></div>
      <div class="row"><button id="send">Send to the session</button><span class="note" id="sendnote">Read at the next board update. For an immediate wake, comment on the page and choose Send to Claude.</span></div>
    </section>
  </div>
  <section><h2>Done today</h2><ul class="done" id="done"></ul></section>
</div>
<script id="snapshot" type="application/json">__STATE__</script>
<script>
(function(){
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
  const el = id => document.getElementById(id);
  function ago(epoch){ if(!epoch) return ""; const s = Math.max(0, Math.floor(Date.now()/1000 - epoch)); return s < 90 ? `${s}s ago` : s < 5400 ? `${Math.round(s/60)} min ago` : `${(s/3600).toFixed(1)} h ago`; }
  let last = null;
  function render(st){
    last = st;
    const r = st.run, live = r.remaining > 0 && !r.paused, word = r.paused ? "PAUSED" : (live ? "RUNNING" : "FINISHED");
    el("strip").innerHTML = `<span class="live"><span class="dot ${live?"":"off"}"></span>${word} &middot; ${esc(r.name)}</span>
      <span class="eta">trial <b>${r.done}</b> of <b>${r.total}</b>${r.remaining>0?` &middot; remaining <b>${esc(r.eta)}</b>`:""}</span>
      <span class="upd" id="upd">updated ${esc(st.updated)} (${ago(st.updated_epoch)})</span>`;
    el("runname").textContent = r.name;
    el("tallies").innerHTML = (r.arms || Object.keys(r.tallies)).map(a => { const t = r.tallies[a] || {};
      return `<div class="tally"><span class="arm">${a}</span><span class="big mono">${t.arrived||0}<small> / ${t.valid||0} valid</small></span><small>${t.invalid||0} invalid &middot; prompt on screen ${t.prompt_on_screen||0} of ${t.executed||0} legs</small></div>`; }).join("");
    el("rows").innerHTML = `<tr><th>#</th><th>arm</th><th>outcome</th><th>leg</th><th>setup</th><th>leg-end class</th><th>prompt on screen</th></tr>` +
      r.rows.map(x => `<tr><td class="n">${x.trial}</td><td><span class="chip arm">${esc(x.arm)}</span></td>
        <td><span class="chip ${x.outcome}">${x.outcome.toUpperCase()}</span>${x.why?` <span class="note">${esc(x.why)}</span>`:""}</td>
        <td class="n">${x.leg_s!=null?Math.round(x.leg_s)+"s":"—"}</td><td class="n">${x.setup_s!=null?Math.round(x.setup_s)+"s":"—"}</td>
        <td>${(x.kinds||[]).map(esc).join(", ")||"—"}</td>
        <td>${x.prompt_on_screen==null?"—":x.prompt_on_screen?`<span class="chip on">YES</span>`:"no"}</td></tr>`).join("");
    el("queue").innerHTML = st.queue.map(q => `<li class="${esc(q.state)}"><span class="state">${esc(q.state)}</span><div><b>${esc(q.title)}</b><p>${esc(q.detail)}</p>${q.blocked_on?`<p class="on">waits on ${esc(q.blocked_on)}</p>`:""}</div></li>`).join("");
    el("decisions").innerHTML = st.decisions.map(d => `<li><b>${esc(d.title)}</b> — ${esc(d.detail)}</li>`).join("");
    el("done").innerHTML = st.done.map(d => `<li><code>${esc(d.hash)}</code> ${esc(d.title)}</li>`).join("");
    el("talk").textContent = st.talk;
  }
  render(JSON.parse(document.getElementById("snapshot").textContent));
  setInterval(() => { const u = el("upd"); if (u && last) u.textContent = `updated ${last.updated} (${ago(last.updated_epoch)})`; }, 15000);
  // ---- messages to the session: an inbox document, replies come back in the state doc
  let inbox = [];
  function renderMsgs(){
    const rep = (last && last.replies) || [];
    const items = [...inbox.map(x => ({...x, who:"you"})), ...rep.map(x => ({...x, who:"me"}))]
      .sort((a,b) => (a.ts||0) - (b.ts||0)).slice(-12);
    el("msgs").innerHTML = items.map(x => `<div class="msg ${x.who}"><small>${x.who==="you"?"you":"the session"} &middot; ${esc(x.when||"")}</small>${esc(x.text)}</div>`).join("");
  }
  if (window.claude && typeof window.claude.use === "function") {
    window.claude.use("db").then(db => {
      if (!db) return;
      db.doc("dash/state").onSnapshot(snap => { if (snap.exists) { render(snap.data()); renderMsgs(); } }, () => {});
      const inboxRef = db.doc("dash/inbox");
      inboxRef.onSnapshot(snap => { inbox = (snap.exists && snap.data().messages) || []; renderMsgs(); }, () => {});
      el("send").onclick = async () => {
        const text = el("m").value.trim(); if (!text) return;
        el("send").disabled = true;
        try {
          const cur = await inboxRef.get();
          const msgs = ((cur.exists && cur.data().messages) || []).slice(-40);
          const d = new Date();
          msgs.push({ ts: Math.floor(d.getTime()/1000), when: d.toLocaleString(), text });
          await inboxRef.set({ messages: msgs });
          el("m").value = ""; el("sendnote").textContent = "Sent. The session reads this at its next board update.";
        } catch (e) { el("sendnote").textContent = "Could not send (" + (e && e.code || "error") + "). Use a comment sent to Claude instead."; }
        finally { el("send").disabled = false; }
      };
    }).catch(() => {});
    // ---- ask the board: a memory-less Claude given the board's data
    window.claude.use("sample").then(sample => {
      if (!sample) return;
      el("askbox").hidden = false;
      const turns = [];
      let ctl = null;
      const copy = { not_granted: "Claude is not allowed on this page for you; the message box still works.", sampling_disabled: "Claude is not available on this account.", rate_limited: "Too many questions for now; try again in a minute.", session_expired: "Sign in again to ask.", refused: "That question was declined; try phrasing it differently.", empty_completion: "No answer came back; ask something smaller.", upstream_error: "The connection dropped; ask again.", prompt_too_large: "The board is too big to send; ask a narrower question." };
      const HIDE = new Set(["not_granted","sampling_disabled","not_declared","capability_disabled","capability_removed"]);
      el("stop").onclick = () => ctl && ctl.abort();
      el("q").addEventListener("keydown", e => { if (e.key === "Enter") el("ask").click(); });
      el("ask").onclick = async () => {
        const q = el("q").value.trim(); if (!q || !last) return;
        const rules = "You are the assistant for this project dashboard (Auto Baseball: a bot that walks a character to a card dealer's table in a PS5 game; an A/B of two ways to walk the last leg is running). Answer the viewer's question from the BOARD DATA below only, briefly and plainly; INVALID trials are not failures. You are NOT the live Claude session doing the work: if the viewer wants to instruct it, tell them to use 'Message the session' or a comment sent to Claude. Board data (JSON):\n" + JSON.stringify(last).slice(0, 40000);
        turns.push({ role: "user", content: q });
        ctl = new AbortController();
        el("ask").disabled = true; el("stop").hidden = false; el("answer").textContent = "Thinking..."; el("asknote").textContent = "";
        try {
          const { text, truncated } = await sample([{ role: "user", content: rules }, ...turns.slice(-8)], {
            modelTier: "quick", cache: false, signal: ctl.signal, onText: ({ text }) => { el("answer").textContent = text; } });
          turns.push({ role: "assistant", content: text });
          if (truncated) el("asknote").textContent = "Cut short; ask for less at a time.";
        } catch (e) {
          if (e && e.text) el("answer").textContent = e.text; else if (!e || e.code !== "cancelled") el("answer").textContent = "";
          if (e && HIDE.has(e.code)) { el("askbox").hidden = true; }
          else if (e && e.code !== "cancelled") el("asknote").textContent = copy[e.code] || copy.upstream_error;
        } finally { el("ask").disabled = false; el("stop").hidden = true; ctl = null; }
      };
    }).catch(() => {});
  }
})();
</script>
'''


def main():
    # Offline tool: hold every input path OFF -- but only when RUN as a script.
    # Set at import this flag disabled stick injection inside a live harness that
    # imported this module for its read() (prompt_zone, 2026-09-07).
    os.environ.setdefault("BASEBALL_TEST_RUN", "1")
    st = build_state()
    json.dump(st, open(STATE, "w"), indent=1)
    open(HTML, "w").write(PAGE.replace("__STATE__", json.dumps(st).replace("</", "<\\/")))
    print(f"  state -> {os.path.relpath(STATE, ROOT)}   html -> {HTML}")
    print(f"  {st['run']['done']}/{st['run']['total']} trials, remaining {st['run']['eta']}")
    for a, t in st["run"]["tallies"].items():
        print(f"  {a:9} {t}")


if __name__ == "__main__":
    main()
