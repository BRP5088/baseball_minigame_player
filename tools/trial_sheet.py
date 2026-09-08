"""Contact sheet + manifest for one trial of the CURRENT chain run, for a reader agent.

    .venv/bin/python -B tools/trial_sheet.py <trial number> [<log>]

Pairs the trial's newest journal with its shots directory by time, writes
agent_progress/closed-loop/review/cur_tNN_<OUTCOME>.jpg (every third frame,
labelled it<iteration> k<estimate> <action>), and prints a JSON manifest the
reader prompt takes verbatim. The user's standing rule (2026-09-07): on every
failed trial, a reader looks at the frames before anything is changed.
"""
import glob, json, os, re, sys

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# THE ARM LABEL IS THE ARMED FLAG'S OWN NAME (chain_trials `--flag`), not
# always "pan-": `--flag STOP_LOOK_YAW` writes `STOP_LOOK_YAW-on`. A pattern
# that only knew "pan-" did not mis-parse those lines, it REFUSED every one of
# them ("cannot parse the trial line") for the whole batch -- and this tool is
# what the user's standing rule runs on every failed trial. Hoisted so a test
# can reach it without the console, cv2 or a log on disk.
LINE_RE = re.compile(
    r"\[ *(\d+)\] (\w+)\s+(?:([A-Za-z_][\w.]*-(?:on|off))\s+)?"
    r"k=(\d+)/\d+\s+it=(\d+)\s+pushes=(\d+)\s+seconds=([\d.]+)"
    r".*?failure=(.*)")


def main(tn, log=os.path.join(ROOT, "overnight", "chain_trials.log")):
    line = next((l for l in open(log) if re.match(r"\[ *%d\] " % tn, l)), None)
    if line is None:
        raise SystemExit(f"no line for trial {tn} in {log}")
    m = LINE_RE.match(line.strip())
    if m is None:
        raise SystemExit(f"cannot parse the trial line: {line.strip()}")
    outcome, arm, k, it, pushes, secs, failure = m.group(2), m.group(3), int(m.group(4)), int(m.group(5)), int(m.group(6)), float(m.group(7)), m.group(8)
    journals = sorted(glob.glob(os.path.join(ROOT, "overnight", "chain_journals", f"route_user_1853_t{tn:02d}_*.jsonl")),
                      key=lambda p: int(re.search(r"_(\d{10})\.jsonl$", p).group(1)))
    j = journals[-1]
    jt = int(re.search(r"_(\d{10})\.jsonl$", j).group(1))
    dirs = sorted(glob.glob(os.path.join(ROOT, "overnight", "chain_frames", "t*")), key=lambda p: int(os.path.basename(p)[1:]))
    d = next(p for p in dirs if jt <= int(os.path.basename(p)[1:]) // 1000 <= jt + 90)
    rows = [json.loads(l) for l in open(j)]
    fs = sorted(glob.glob(os.path.join(d, "it_[0-9][0-9][0-9]_k*[0-9].jpg")), key=lambda p: int(re.search(r"it_(\d+)_", p).group(1)))
    ims = []
    for p in fs[::3]:
        im = cv2.resize(cv2.imread(p), (320, 180)); itn = int(re.search(r"it_(\d+)_", p).group(1))
        row = next((r for r in rows if r["iteration"] == itn), None)
        cv2.putText(im, f"it{itn} k{row['k']} {row['action'][:12]}" if row else f"it{itn}", (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
        ims.append(im)
    rws = [cv2.hconcat(ims[i:i + 6]) for i in range(0, len(ims), 6)]
    w = rws[0].shape[1]
    rws = [cv2.copyMakeBorder(r, 0, 0, 0, w - r.shape[1], cv2.BORDER_CONSTANT) for r in rws]
    out_dir = os.path.join(ROOT, "agent_progress", "closed-loop", "review"); os.makedirs(out_dir, exist_ok=True)
    sheet = os.path.join(out_dir, f"cur_t{tn:02d}_{outcome}_{jt}.jpg")
    cv2.imwrite(sheet, cv2.vconcat(rws))
    acts = {}
    for r in rows:
        acts[r["action"]] = acts.get(r["action"], 0) + 1
    print(json.dumps({"batch": "cur", "trial": f"{tn:02d}", "arm": arm, "outcome": outcome, "k": k, "seconds": secs, "failure": failure[:90],
                      "actions": acts, "sheet": os.path.relpath(sheet, ROOT), "journal": os.path.relpath(j, ROOT)}, separators=(",", ":")))


if __name__ == "__main__":
    main(int(sys.argv[1]), *(sys.argv[2:3]))
