"""READ-ONLY: extract every execution of office_door -> portrait_room from the
archived logs that ran on the RESTORED leg 1 (after commit aa773dc, 2026-09-06
22:34), and report per execution:    got[k]   the achieved heading the executor walked step k at (from the
             "step k/16 bearing B (got G)" line)
    noop[k]  whether turn_to sent nothing at step k
    dx       the PRE-alignment lateral offset align_at_node measured at
             portrait_room (first "align: step 1/6 dx=" or "within 35px (dx=")
             after "align at portrait_room: yaw nulled")and then two derived numbers the doorway A/B depends on:    (a) what heading the doorway traverse (steps 10-15, 1-based) was actually
        walked at, and its spread;
    (b) how often a +4.0 deg offset on step 10 would have been a NO-OP under
        slow_traverse.TURN_TOLERANCE = 4.0, given the heading at step 9.Logs are read as text. Nothing is written except stdout.
"""
import re
import statistics
import sysROOT = "/Users/bpatterson/Documents/Claude Cowork Personal/Auto Baseball"
LOGS = [
    ("ab_leg1 original arm", ROOT + "/overnight/ab_leg1.log", "original"),
    ("OPEN-5 (ab_attempts)", ROOT + "/overnight/ab_attempts_open5.log", None),
    ("streak (measure_streak)", ROOT + "/overnight/streak.log", None),
]STEP = re.compile(r"step (\d+)/16 bearing\s+([\d.]+) \(got\s+([\d.\-]+)\)")
NOOP = re.compile(r"turn to ([\d.]+): NO-OP")
TURNED = re.compile(r"turn to ([\d.]+): TURNED to ([\d.]+)")
ARM = re.compile(r"arm=(\w+)")
LEG = "leg office_door -> portrait_room"
YAW = "align at portrait_room: yaw nulled"
DX1 = re.compile(r"align: step 1/6 dx=([+\-][\d.]+)")
DX0 = re.compile(r"align: within 35px \(dx=([+\-][\d.]+)\)")
BLOCKED = "blocked sideways"
FINAL = re.compile(r"align at portrait_room: dx ([+\-][\d.]+)px")def wrap(a):
    return (a + 180.0) % 360.0 - 180.0def parse(path, want_arm):
    execs = []
    arm = None
    cur = None
    await_dx = False
    for line in open(path, errors="replace"):
        m = ARM.search(line)
        if m:
            arm = m.group(1)
        if LEG in line:
            if cur is not None:
                execs.append(cur)
            cur = {"arm": arm, "got": {}, "noop": {}, "dx": None,
                   "dx_final": None, "blocked": False}
            await_dx = False
            continue
        if cur is None:
            continue
        m = STEP.search(line)
        if m:
            k = int(m.group(1))
            g = m.group(3)
            # "got --" is an UNREAD heading (turn_to abandoned before turning);
            # keep the step but record no heading for it.
            cur["got"][k] = None if g == "--" else float(g)
            cur["bearing_" + str(k)] = float(m.group(2))
            continue
        m = NOOP.search(line)
        if m and "office_door" not in line:
            # the next step line will claim this heading; record the no-op
            # against the step count reached so far + 1
            cur["noop"][len(cur["got"]) + 1] = True
            continue
        if YAW in line:
            await_dx = True
            continue
        if await_dx:
            m = DX1.search(line) or DX0.search(line)
            if m:
                cur["dx"] = float(m.group(1))
                await_dx = False
                continue
        if BLOCKED in line and cur["dx"] is not None and cur["dx_final"] is None:
            cur["blocked"] = True
        m = FINAL.search(line)
        if m and cur["dx_final"] is None:
            cur["dx_final"] = float(m.group(1))
            # once aligned at portrait_room this execution is complete
            execs.append(cur)
            cur = None
    if cur is not None:
        execs.append(cur)
    if want_arm:
        execs = [e for e in execs if e["arm"] == want_arm]
    return execsdef report(label, execs):
    print(f"\n=== {label}: {len(execs)} executions of office_door -> portrait_room")
    full = [e for e in execs if len(e["got"]) == 16
            and all(e["got"].get(k) is not None for k in range(9, 16))]
    unread = sum(1 for e in execs if len(e["got"]) == 16) - len(full)
    print(f"    completed all 16 steps with steps 9-15 read: {len(full)}   "
          f"(+{unread} with an unread heading in 9-15)   "
          f"reached portrait_room alignment (dx measured): "
          f"{sum(1 for e in execs if e['dx'] is not None)}")
    # (a) traverse heading, steps 10..15 (1-based) == map indices 9..14
    trav = []
    for e in full:
        hs = [wrap(e["got"][k]) for k in range(10, 16)]
        trav.append(hs)
    if trav:
        means = [statistics.mean(h) for h in trav]
        spreads = [max(h) - min(h) for h in trav]
        print(f"    traverse heading (steps 10-15), per execution mean: "
              + " ".join(f"{m:+.1f}" for m in means))
        print(f"      pooled: mean {statistics.mean(means):+.2f}  "
              f"sd {statistics.pstdev(means):.2f}  "
              f"min {min(means):+.1f}  max {max(means):+.1f}   "
              f"(recorded bearing mean -1.35, recorded cam mean +0.74)")
        print(f"      within-execution spread over the six steps: "
              f"median {statistics.median(spreads):.2f} deg, max {max(spreads):.2f}")
    # (b) would +4.0 on step 10 be a NO-OP?  target = bearing10 + 4.0 ; err vs got9
    noops = 0
    n = 0
    errs = []
    for e in full:
        b10 = e.get("bearing_10")
        g9 = e["got"][9]
        if b10 is None:
            continue
        err = wrap((b10 + 4.0) - g9)
        errs.append(err)
        n += 1
        if abs(err) <= 4.0:
            noops += 1
    if n:
        print(f"    +4.0 offset on step 10 would be a NO-OP (|err|<=4.0) in "
              f"{noops}/{n};  err = "
              + " ".join(f"{x:+.1f}" for x in errs))
    # how many of steps 10..15 were NO-OPs as actually run
    nn = [sum(1 for k in range(10, 16) if e["noop"].get(k)) for e in full]
    if nn:
        print(f"    NO-OP turns among steps 10-15 as run: per execution {nn}  "
              f"(6 = the whole traverse was walked at the step-9 heading)")
    # dx at portrait_room
    dxs = [e["dx"] for e in execs if e["dx"] is not None]
    if dxs:
        pos = sum(1 for d in dxs if d > 0)
        print(f"    PRE-alignment dx at portrait_room (n={len(dxs)}): "
              + " ".join(f"{d:+.1f}" for d in dxs))
        print(f"      median {statistics.median(dxs):+.1f}  mean "
              f"{statistics.mean(dxs):+.1f}  sd {statistics.pstdev(dxs):.1f}  "
              f"positive {pos}/{len(dxs)}   |dx|>35 (needs a correction): "
              f"{sum(1 for d in dxs if abs(d) > 35)}/{len(dxs)}   "
              f"blocked sideways: {sum(1 for e in execs if e['blocked'])}")
    # association: traverse heading vs dx (observational only, 10.2)
    pairs = [(statistics.mean([wrap(e["got"][k]) for k in range(10, 16)]), e["dx"])
             for e in full if e["dx"] is not None]
    if len(pairs) >= 4:
        xs, ys = zip(*pairs)
        mx, my = statistics.mean(xs), statistics.mean(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        sxy = sum((x - mx) * (y - my) for x, y in pairs)
        syy = sum((y - my) ** 2 for y in ys)
        r = sxy / ((sxx * syy) ** 0.5) if sxx and syy else float("nan")
        slope = sxy / sxx if sxx else float("nan")
        print(f"    heading-vs-dx (OBSERVATIONAL, n={len(pairs)}): "
              f"r = {r:+.2f}, slope {slope:+.1f} px per deg of traverse heading")
    return fullif __name__ == "__main__":
    allx = []
    for label, path, arm in LOGS:
        try:
            ex = parse(path, arm)
        except FileNotFoundError:
            print(f"\n=== {label}: MISSING {path}")
            continue
        allx += report(label, ex)
    print("\n=== POOLED over the three restored-leg-1 logs")
    report("pooled", allx)
