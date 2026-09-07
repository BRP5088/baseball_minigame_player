"""Controller review patch (manager, 2026-09-07). APPLY ONLY AFTER workflow wf_1a357a4f-1a7 has finished.

Three gaps found reading chain_walk.py against the recorder's output:
 1. CORNER CUTTING. ~40% of an executor-recorded chain is STATIONARY (turns and the
    0.35 s settles between pushes). The loop turns to every waypoint's heading and
    PUSHES 0.4 s toward it, so at a 90-degree corner it pushes along each intermediate
    heading of the turn: a curve into the inside wall. Fix: build a PLAN from the
    chain -- walking frames every STRIDE, and each stationary run collapsed to ONE
    turn-only waypoint (its last heading). Turn-only targets: turn, no push, no locate.
 2. THE PROMPT CHECK WAS GATED TO THE LAST 3 WAYPOINTS. If k lags while the character
    already stands in the prompt, at_table() is never asked and the loop escapes
    (jumps, sidesteps) at a won table -- the exact thing the user watched. at_table()
    has 0 false positives on 693 non-table frames and costs ~ms; check it EVERY
    iteration.
 3. NO HEADING FALLBACK. The compass abstains on 6-15% of frames; a turn-only
    waypoint with heading None would skip the turn at a corner. Fallback: the
    recorder's commanded `cam`, then the last known heading.
Also: chain.py's Chain.load must pass `cam` through (it writes lx/ly/note only), and
chain_trials.py passes progress_file="progress_testing.json" like every live runner.
"""
PLAN_FN = '''
# The recorder samples every 0.25 s; the executor it recorded walks at ~0.35, so
# one frame is ~0.09 u and one 0.45 x 0.40 s push is ~0.18 u (§6). STRIDE 2 makes
# a walking waypoint about one push apart. Not measured live -- logged per trial.
STRIDE = 2
# |stick| at or under this is "not walking" (the tap records the commanded value;
# a settle or a turn is exactly 0.0). Frames with ly None (no tap) count as walking.
STATIONARY_STICK = 0.05


def plan_indices(wps, stride=STRIDE):
    """The chain indices to visit, as (index, push, heading) triples.

    Walking frames every `stride`; each STATIONARY run (turns, settles) collapses
    to ONE turn-only entry carrying the run's last heading, so a corner is turned
    on the spot instead of pushed around. Heading falls back to the recorder's
    commanded `cam`, then to the last known heading, so an abstaining compass
    cannot silently skip a corner. Index 0 (the trusted spawn) is never a target;
    the final waypoint always is.
    """
    plan, run, last_heading, walked = [], [], None, 0
    n = len(wps)
    for i, w in enumerate(wps):
        heading = getattr(w, "heading", None)
        if heading is None:
            heading = getattr(w, "cam", None)
        if heading is None:
            heading = last_heading
        else:
            last_heading = heading
        lx = getattr(w, "lx", None) or 0.0
        ly = getattr(w, "ly", None)
        stationary = (ly is not None and abs(ly) <= STATIONARY_STICK
                      and abs(lx) <= STATIONARY_STICK)
        if i == 0:
            continue
        if stationary:
            run.append((i, heading))
            continue
        if run:
            plan.append((run[-1][0], False, run[-1][1]))
            run, walked = [], 0
        if walked % stride == 0:
            plan.append((i, True, heading))
        walked += 1
    if run:
        plan.append((run[-1][0], False, run[-1][1]))
    if n > 1 and (not plan or plan[-1][0] != n - 1):
        plan.append((n - 1, True, last_heading))
    return plan
'''
print("patch text ready; apply by hand against the FINAL chain_walk.py (anchors will have moved)")

# ADDED after Snoopy's review (qwen2.5-coder:14b, one real gap of nine):
# chain_record._drive_executor: after each attempt, count lines with heading
# not None and with cam not None; log "headings h/n  cam c/n"; if BOTH are zero,
# do not keep the chain (rename *_noheading_<n>) -- a dead compass otherwise
# yields a chain that looks complete and a controller that never turns.
