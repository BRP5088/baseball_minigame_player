"""Per-leg arrival record, so SPEED follows PROVEN RELIABILITY automatically.

THE POLICY (user, 2026-09-04): "of course I want the segments of the route that
have been proven to be reliable to be fast to maximize trial time/count. make
the unknown/unproven segments slow with intention."

Explore slow, exploit fast — but not as two flags somebody has to remember to
set. A leg that has earned speed gets it; a leg that starts failing loses it
again on its own. The alternative is a hand-maintained list that goes stale
exactly when it matters, i.e. when behaviour changes.

MEASURED, the record this starts from (n=76 leg executions):

    office_door -> portrait_room     20/20   1.000   fast
    portrait_room -> bar_pool_room   14/21   0.667   normal
    bar_pool_room -> bar_jukebox      6/15   0.400   normal

The bar is deliberately high. Speeding a leg up costs repeatability — measured
displacement spread per push is ~15px at 0.25-0.45 and 476px at 0.85 — so a leg
must be genuinely dependable before it is worth spending that.
"""

import json
import os

# ANCHORED ON THIS FILE, NOT THE CWD. This was "leg_reliability.json", which
# resolves against wherever the process happened to be started — so a run
# launched from overnight/ read and created a DIFFERENT record, and a leg's
# earned speed came and went with the working directory with nothing saying so.
# compass._SCALE_CACHE_FILE and input_controller._VIEW_CACHE_FILE are anchored
# the same way for the same reason. The resolved path is unchanged for anything
# started from the project root, which is every caller today.
STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "leg_reliability.json")

# Set by _load() when the store was PRESENT but unusable, so "the record is
# empty" can be told apart from "the record was lost". A corrupt record must
# not stop a walk — and note that raising could not make it visible anyway,
# because graph_walk wraps BOTH call sites in `except Exception` (leg_scale at
# :1202, record at :1585). Visibility here has to be a warning plus this flag.
LAST_CORRUPTION = None

# A leg must have this many recorded attempts before speed is considered at all.
# Below it the rate is noise: n=3 has power 0.00 to resolve even a large
# difference on this project.
MIN_ATTEMPTS = 10

# ... and must have arrived at least this often. 0.95 keeps a wide margin over
# the best non-perfect leg measured (0.667), so this cannot creep down onto a
# merely-decent leg.
MIN_RATE = 0.95

FAST_SCALE = 3.0        # what a proven leg gets
NORMAL_SCALE = 1.0      # what everything else gets, including unknown ground


def _warn(msg):
    # Plain print, like orchestrator._load_learned_roster, whose warnings this
    # mirrors. During a run stdout IS the log that gets read.
    print(f"WARNING: {msg}")


def _load(path=STORE):
    """The record, or {} — and SAY SO when {} means the record was LOST.

    A corrupt record still degrades to {}, because bookkeeping must never stop
    a walk. What it must not do is degrade SILENTLY: an empty return is
    indistinguishable from "nothing recorded yet", so a leg that had earned
    FAST_SCALE would drop back to NORMAL_SCALE with nothing in the log to say
    why, and the next record() would overwrite the evidence. That is the
    diagnosis-catalogue shape exactly — the code did nothing, and doing nothing
    looked just like working.

    NOT DETECTABLE, and not claimed: a truncation that happens to land on valid
    JSON (a file cut to "{}") is indistinguishable from an empty record. The
    atomic write below is what prevents that case, rather than this check.
    """
    global LAST_CORRUPTION
    LAST_CORRUPTION = None
    if not os.path.exists(path):
        return {}                       # no record yet is NOT corruption
    try:
        with open(path) as fh:
            raw = json.load(fh)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        LAST_CORRUPTION = f"{path} is unreadable ({exc})"
        _warn(f"{LAST_CORRUPTION} — every leg falls back to the slow scale.")
        return {}
    if not isinstance(raw, dict):
        LAST_CORRUPTION = f"{path} is not an object ({type(raw).__name__})"
        _warn(f"{LAST_CORRUPTION} — every leg falls back to the slow scale.")
        return {}
    out = {}
    for key, e in raw.items():
        # Valid JSON of the WRONG SHAPE. rate() and report() both index
        # e["attempts"] straight, so one malformed row raises a KeyError out of
        # a module that promises never to end a run — and graph_walk would
        # swallow it, losing every OTHER leg's record invisibly. Skip the row,
        # keep the rest.
        try:
            attempts, arrived = int(e["attempts"]), int(e["arrived"])
        except (TypeError, ValueError, KeyError, AttributeError, IndexError):
            LAST_CORRUPTION = f"malformed entry {key!r} in {path}"
            _warn(f"skipping {LAST_CORRUPTION}.")
            continue
        # arrived > attempts is a rate above 1.0, which would EARN FAST_SCALE
        # off a nonsense row. Speed costs repeatability (displacement spread
        # ~15px at 0.25-0.45 against 476px at 0.85), so it must never be
        # granted by a number that cannot be true.
        if attempts < 0 or arrived < 0 or arrived > attempts:
            LAST_CORRUPTION = (f"impossible entry {key!r} in {path} "
                               f"({arrived}/{attempts})")
            _warn(f"skipping {LAST_CORRUPTION}.")
            continue
        out[key] = {"attempts": attempts, "arrived": arrived}
    return out


def _quarantine(path):
    """Move an unreadable record aside instead of writing over it.

    record() is a read-modify-write. Over a record it could not read, a plain
    write destroys the ONLY copy of whatever went wrong and resets every leg to
    zero attempts in the same stroke — so the corruption erases its own
    evidence and the reset looks like a fresh install.
    """
    dest = path + ".corrupt"
    try:
        os.replace(path, dest)
        _warn(f"kept the unreadable record at {dest} rather than "
              f"overwriting it; {path} now restarts from zero.")
    except OSError as exc:
        _warn(f"could not preserve the unreadable record ({exc}).")


def _atomic_write_json(path, data):
    """Write through a temp file + rename, so an interrupted write can never
    leave a truncated record behind.

    The same pattern as orchestrator._atomic_write_json,
    input_controller._save_view_cache and compass._save_scale_cache, whose
    comment gives the reason: this file "now lives on a NAS. A plain open('w')
    truncates first, so a dropped mount mid-write leaves an empty file."
    os.replace is atomic within a filesystem, so a reader sees the whole old
    record or the whole new one and never half of either.

    NOT CLAIMED: this does not make concurrent writers safe. record() is still
    an unlocked read-modify-write, so two processes racing can still lose one
    update — it just cannot lose the FILE.
    """
    tmp = f"{path}.tmp"
    try:
        with open(tmp, "w") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        # The real guarantee (a reader never sees a partial file) holds without
        # this — os.replace simply never runs. But a crash mid-write otherwise
        # ORPHANS the .tmp, and a stale one sitting beside the record invites
        # someone to wonder which is real.
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _key(a, b):
    return f"{a}->{b}"


def record(a, b, arrived, path=STORE):
    """Note one attempt at a leg."""
    d = _load(path)
    if LAST_CORRUPTION is not None:
        _quarantine(path)
    e = d.setdefault(_key(a, b), {"attempts": 0, "arrived": 0})
    e["attempts"] += 1
    if arrived:
        e["arrived"] += 1
    _atomic_write_json(path, d)
    return e


def rate(a, b, path=STORE):
    """(arrival rate, attempts) — (None, n) when there is not enough to judge."""
    e = _load(path).get(_key(a, b))
    if not e or not e["attempts"]:
        return None, 0
    return e["arrived"] / e["attempts"], e["attempts"]


def scale_for(a, b, path=STORE):
    """The speed scale this leg has EARNED. Unproven ground stays slow."""
    r, n = rate(a, b, path)
    if r is None or n < MIN_ATTEMPTS or r < MIN_RATE:
        return NORMAL_SCALE
    return FAST_SCALE


def report(path=STORE):
    out = []
    for k, e in sorted(_load(path).items()):
        r = e["arrived"] / e["attempts"] if e["attempts"] else 0.0
        a, _, b = k.partition("->")
        out.append((k, e["arrived"], e["attempts"], r, scale_for(a, b, path)))
    return out
