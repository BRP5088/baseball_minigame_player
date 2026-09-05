"""Record RICH BUT UNRECOGNISED frames seen while walking, as map candidates.

WHY. A quarter of route failures are OVERSHOT: the frame is full of detail
(744-1500 keypoints) but `identify()` names nothing, because the character has
walked somewhere the map has no reference for — an unmapped hallway, in the one
frame that was ever captured of it. When that happens the run is blind: it
cannot route back, so it resets and re-walks everything.

Those places can only be mapped if something looks at them, and until now
nothing did. The route walks through them several times a trial and throws every
frame away.

WHY IT IS AFFORDABLE NOW. Surveying costs one `places.identify()` per sample —
43ms. The frames themselves are already being captured for the view-change
measurement, so they are free. Before tesserocr, a bearing read alone cost
261ms and there was no budget for this; read_bearing is now 31ms.

WHAT IT DOES NOT DO. It does not add anything to the map. A place seeded from a
bad frame poisons the localiser permanently — a near-featureless upstairs door
once matched the bar at 0.906, outscoring every genuine arrival — so candidates
are only ever WRITTEN TO DISK for a human or an offline pass to judge.
"""

import json
import os
import time

# A candidate must be at least this rich to be worth keeping. The same bar
# brett_walk.mark() uses, and for the same reason: below it a reference matches
# every other blank frame.
MIN_KEYPOINTS = 400

# ... and must be clearly UNrecognised. A frame the localiser already names is
# not a new place, and one it half-names is exactly the ambiguity that should
# not become a reference.
MAX_MATCHES = 120

SURVEY_DIR = "survey"


def consider(img, where, log=None):
    """Keep `img` if it looks like an unmapped place. Returns a path or None.

    `where` is free-form context (leg, step) so a candidate can be traced back
    to the moment it was seen.
    """
    import places

    _, desc = places.keypoints(img)
    n = 0 if desc is None else len(desc)
    if n < MIN_KEYPOINTS:
        return None                      # featureless: a wall, not a place
    room, score, margin = places.identify(img)
    if room is not None or score > MAX_MATCHES:
        return None                      # already known, or ambiguous

    os.makedirs(SURVEY_DIR, exist_ok=True)
    stamp = int(time.time() * 1000)
    path = os.path.join(SURVEY_DIR, f"cand_{stamp}.jpg")
    img.save(path)
    meta = {"file": path, "keypoints": n, "best_match": score,
            "margin": margin, "where": where}
    with open(os.path.join(SURVEY_DIR, "candidates.jsonl"), "a") as fh:
        fh.write(json.dumps(meta) + "\n")
    if log:
        log(f"      surveyed an unmapped view: {n} keypoints, best match "
            f"{score:.0f} — saved {path}")
    return path


def load(path=SURVEY_DIR):
    """Every candidate recorded so far."""
    f = os.path.join(path, "candidates.jsonl")
    if not os.path.exists(f):
        return []
    out = []
    for line in open(f):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out
