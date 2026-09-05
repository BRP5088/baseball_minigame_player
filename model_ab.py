"""Compare Haiku against Sonnet on real captured frames, offline.

Swapping the model and hoping is not a test. This runs BOTH against the same
frames, using the orchestrator's own reading function and prompt, and reports
where they disagree and how long each took.

    BASEBALL_API_BUDGET=40 python3 model_ab.py 6

Agreement is the metric that matters. There is no ground truth here — nobody has
labelled these frames — so what this can honestly show is whether the cheaper
model says the SAME THING as the one currently trusted. Disagreement means
somebody has to look; agreement across varied frames is reasonable evidence the
cheaper model is not worse.
"""

import glob
import json
import os
import sys
import time

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-5"


def read_with(model, img, orch):
    """Read one frame with a given model, returning (result, seconds)."""
    old = orch.MODEL
    orch.MODEL = model
    t0 = time.time()
    try:
        out = orch.read_ban_row_cards(img)
    finally:
        orch.MODEL = old
    return out, time.time() - t0


def normalise(cards):
    """Comparable form: names case- and space-insensitive, numbers exact.

    Card NAMES differ only in presentation between the two models — one returns
    "Johnny Drawers", the other "JOHNNY DRAWERS" — and downstream matching is
    case-insensitive anyway. Comparing raw strings therefore reports cosmetic
    differences as disagreements and buries the ones that matter.
    """
    out = []
    for c in cards or []:
        name = " ".join(str(c.get("name", "")).split()).upper()
        out.append((name, c.get("power"), c.get("secondary")))
    return out


def classify(a, b):
    """How two readings differ: identical / case-only / values / membership."""
    if a == b:
        return "identical"
    na, nb = normalise(a), normalise(b)
    if na == nb:
        return "case-only"
    names_a = {n for n, _, _ in na}
    names_b = {n for n, _, _ in nb}
    if names_a != names_b:
        return "different cards"
    by_a = {n: (p, s) for n, p, s in na}
    for n, p, s in nb:
        if by_a[n] != (p, s):
            return "different values"
    return "other"


def compare(n=6, log=print):
    os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")
    from PIL import Image
    import orchestrator as orch

    frames = sorted(glob.glob("test_fixtures/harvest/*.jpg"))
    if not frames:
        log("  no harvested frames to test against")
        return
    # spread across the capture rather than taking consecutive near-duplicates
    step = max(1, len(frames) // n)
    picks = frames[::step][:n]
    log(f"  {len(picks)} frames, {2 * len(picks)} API calls\n")

    agree = 0
    kinds = {}
    times = {HAIKU: [], SONNET: []}
    for f in picks:
        img = Image.open(f)
        try:
            s_out, s_t = read_with(SONNET, img, orch)
            h_out, h_t = read_with(HAIKU, img, orch)
        except Exception as exc:
            log(f"  {os.path.basename(f)}: stopped ({exc})")
            break
        times[SONNET].append(s_t)
        times[HAIKU].append(h_t)
        kind = classify(s_out, h_out)
        kinds[kind] = kinds.get(kind, 0) + 1
        # case-only differences are not disagreements about what is on screen
        if kind in ("identical", "case-only"):
            agree += 1
        log(f"  {os.path.basename(f)}: {kind:16} "
            f"({len(s_out or [])} vs {len(h_out or [])} cards)  "
            f"sonnet {s_t:.1f}s / haiku {h_t:.1f}s")
        if kind in ("different cards", "different values"):
            sa, sb = normalise(s_out), normalise(h_out)
            only_s = [c for c in sa if c not in sb]
            only_h = [c for c in sb if c not in sa]
            if only_s:
                log(f"      sonnet only: {only_s[:3]}")
            if only_h:
                log(f"      haiku  only: {only_h[:3]}")
    done = len(times[SONNET])
    if done:
        log(f"\n  --- {done} frames ---")
        for k in sorted(kinds):
            log(f"    {k:18} {kinds[k]}")
        log(f"  agreement (ignoring case): {agree}/{done} "
            f"({100.0 * agree / done:.0f}%)")
        log(f"  mean latency: sonnet {sum(times[SONNET])/done:.1f}s, "
            f"haiku {sum(times[HAIKU])/done:.1f}s "
            f"({sum(times[SONNET])/max(sum(times[HAIKU]),1e-9):.1f}x faster)")
        real = kinds.get("different cards", 0) + kinds.get("different values", 0)
        log(f"\n  VERDICT: {real}/{done} frames differ in substance. "
            + ("Haiku is a safe swap." if real == 0 else
               "Look at those before swapping — this pipeline treats a "
               "confident wrong read as worse than no read."))


if __name__ == "__main__":
    compare(int(sys.argv[1]) if len(sys.argv) > 1 else 6)
