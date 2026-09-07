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
os.environ.setdefault("BASEBALL_TEST_RUN", "1")
STATE = os.path.join(ROOT, "overnight", "dashboard_state.json")
HTML = os.environ.get("DASH_HTML", os.path.join(
    "/private/tmp/claude-502/-Users-bpatterson-Documents-Claude-Cowork-Personal-Auto-Baseball/e6392fcc-4b59-4ace-b5b6-76c4bf041181/scratchpad",
    "auto_baseball_dashboard.html"))

QUEUE = [
    {"title": "Goal-leg A/B on the console", "state": "done",
     "detail": "Shipped 1/8 vs recorded 1/9, p = 1.0: no arrival difference; the recorded leg is 3x cheaper (65s vs 189s). Written up as OPEN-21."},
    {"title": "Land the control-frame fix", "state": "done",
     "detail": "Landed during the pause (24857d8): start pose and leg-end frame on both outcomes; three mutants caught from a green baseline."},
    {"title": "Land the OCR path in at_table()", "state": "done",
     "detail": "Landed (07cf0cc): mask first, OCR only when the mask says no; three real fixtures, three mutants caught."},
    {"title": "Score the A/B twice and write OPEN-21", "state": "done",
     "detail": "As the harness scored it, and post hoc from the pre-sweep frames with mask + OCR (prompt on screen at the leg's end). Recommend the flag flip if the numbers carry it; the flip is yours."},
    {"title": "Map the prompt zone around the dealer", "state": "running",
     "detail": "Running, third design: a star around the recorded endpoint -- the endpoint first, then 0.05u left/right, 0.10/0.20u back, 0.05u forward -- five headings a point, mask + OCR verdicts, three walks. Both grid attempts wedged in the furniture (right of the endpoint is the chair at 0.10u) and today's route to the jukebox fails most setups."},
    {"title": "Full-route streak with the winner and the better instrument", "state": "next",
     "detail": "Route to the table at attempts=9, ceiling sized as attempts x route time so it cannot censor 7 of 10 again."},
    {"title": "The position failures", "state": "next",
     "detail": "Stopped short at an NPC (trial 2), walked into the neighbouring table (trial 3). The pre-sweep frames say which dominates before anything is built."},
]
DECISIONS = [
    {"title": "Flip GOAL_LEG_AS_RECORDED?", "detail": "Only after the A/B; it changes a default. I will recommend, you decide."},
    {"title": "OCR on the $50 gate", "detail": "Zero false positives measured on 693 clean frames and the quest-log anchor; say if you want to see the json before it lands."},
]


def executed_legs():
    from goal_leg_sheet import executed_legs as _e
    return _e()


def rows_and_tallies():
    import glob
    from PIL import Image
    import table_prompt as tp
    import prompt_ocr_ab as ocr
    j = json.load(open(os.path.join(ROOT, "overnight", "ab_goal_leg.json")))
    runs = j["runs"]
    legs = executed_legs()
    pre = sorted(glob.glob(os.path.join(ROOT, "overnight", "goal_leg_failframes", "at_dealer_table_[0-9]*.jpg")))
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
            outcome = "arrived" if arrived else "missed"
            secs = (r.get("setup_seconds") or 0) + (r.get("seconds") or 0)
            why = ""
        durations.append(secs)
        rows.append({"trial": i, "arm": r["arm"], "outcome": outcome, "why": why,
                     "leg_s": r.get("seconds") if arrived is not None else None,
                     "setup_s": r.get("setup_seconds"),
                     "located": r.get("located"), "recheck": r.get("recheck_at_table"),
                     "kinds": r.get("failure_kinds_leg_end") or [],
                     "prompt_on_screen": prompt.get(i)})
    tallies = {}
    for arm in ("shipped", "recorded"):
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
                           "median_trial_s": round(med)}


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
        "run": {"name": "Goal-leg A/B: shipped vs recorded", "harness": "overnight/ab_goal_leg.py",
                "started": "2026-09-07 09:35", "paused": paused, **run, "rows": rows, "tallies": tallies},
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
      <p class="note">INVALID is not a failure: the leg under test never ran, or the 1200s ceiling cut it off. "Prompt on screen" is the pre-sweep frame re-read with the mask plus OCR — the leg-level criterion the shipped detector cannot see.</p>
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
    el("tallies").innerHTML = ["shipped","recorded"].map(a => { const t = r.tallies[a] || {};
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
    st = build_state()
    json.dump(st, open(STATE, "w"), indent=1)
    open(HTML, "w").write(PAGE.replace("__STATE__", json.dumps(st).replace("</", "<\\/")))
    print(f"  state -> {os.path.relpath(STATE, ROOT)}   html -> {HTML}")
    print(f"  {st['run']['done']}/{st['run']['total']} trials, remaining {st['run']['eta']}")
    for a, t in st["run"]["tallies"].items():
        print(f"  {a:9} {t}")


if __name__ == "__main__":
    main()
