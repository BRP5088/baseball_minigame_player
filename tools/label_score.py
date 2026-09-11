"""Score a labelled batch from tools/label_batch.py against the user's labels.

    .venv/bin/python -B tools/label_score.py <dir> "f00: 2 / none   f01: 3 / 1,3  ..."

Accepts `2/none`, `2 / -`, `2/1,3`, one frame per whitespace-or-newline group. Reports
per-frame agreement for BOTH readers and the populations behind the gate, so a batch
either moves a constant or says it cannot.
"""
import os, sys, json, re

d = sys.argv[1]
raw = " ".join(sys.argv[2:])
ans = {a["frame"]: a for a in json.load(open(os.path.join(d, "answers.json")))}

labels = {}
# the user's own shorthand first:  F03: S0,2C2   /   F06: SC4   /   F09: S3C
for m in re.finditer(r"F?(\d+)\s*:\s*S\s*(none|-|[0-4,\s]*?)\s*C\s*([0-4]|none|-)?",
                     raw, re.I):
    k = int(m.group(1))
    _s = (m.group(2) or "").strip().lower()
    sel = [] if _s in ("", "none", "-") else sorted(int(x) for x in re.findall(r"[0-4]", _s))
    c = (m.group(3) or "").lower()
    labels[k] = (None if c in ("", "none", "-") else int(c), sel)
# and the slash form, for anything already written that way
for m in re.finditer(r"f?(\d+)\s*:\s*([0-4]|none|-)\s*/\s*([0-4,\s]*|none|-)", raw, re.I):
    k = int(m.group(1))
    if k in labels:
        continue
    cur = None if m.group(2).lower() in ("none", "-") else int(m.group(2))
    sel_raw = m.group(3).strip().lower()
    sel = [] if sel_raw in ("", "none", "-") else sorted(
        int(x) for x in re.findall(r"[0-4]", sel_raw))
    labels[k] = (cur, sel)
if not labels:
    print("could not parse any labels — expected e.g.  F00: S0,2C2"); sys.exit(1)

cur_ok = cur_n = sel_ok = sel_n = 0
true_reads, false_reads = [], []
print(f"{'frame':6s} {'cursor':>16s} {'selected':>22s}")
for k in sorted(labels):
    a = ans.get(k)
    if not a or a.get("rows") != 5:
        print(f"f{k:02d}    reader had no usable hand — excluded")
        continue
    cur_t, sel_t = labels[k]
    cur_g, sel_g = a.get("cursor"), sorted(a.get("selected") or [])
    cur_n += 1; sel_n += 1
    cur_ok += (cur_g == cur_t); sel_ok += (sel_g == sel_t)
    glow = a.get("glow") or []
    if cur_t is not None and cur_t < len(glow):
        true_reads.append(glow[cur_t])
        false_reads += [v for i, v in enumerate(glow) if i != cur_t]
    mark = lambda ok: "ok " if ok else "WRONG"
    print(f"f{k:02d}   {str(cur_g):>6s} vs {str(cur_t):<5s} {mark(cur_g==cur_t)}   "
          f"{str(sel_g):>9s} vs {str(sel_t):<9s} {mark(sel_g==sel_t)}")

print()
print(f"  cursor   {cur_ok}/{cur_n}")
print(f"  selected {sel_ok}/{sel_n}")
if true_reads and false_reads:
    print(f"  glow on the TRUE cursor card : min {min(true_reads):.2f}  max {max(true_reads):.2f}  n={len(true_reads)}")
    print(f"  glow on every OTHER card     : max {max(false_reads):.2f}  n={len(false_reads)}")
    band = min(true_reads) - max(false_reads)
    print(f"  empty band {max(false_reads):.2f} .. {min(true_reads):.2f}"
          + (f"   midpoint {(min(true_reads)+max(false_reads))/2:.1f}" if band > 0
             else "   OVERLAP — no gate separates them"))
