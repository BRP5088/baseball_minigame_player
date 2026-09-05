"""machine_id() must not go stale when the display changes mid-process.

WHAT THIS GUARDS
----------------
machine_id() keys every geometry cache on disk: compass_scale.json
(px-per-90-degrees and view centre), view_bounds.json, and
window_reference.json. The id folds in mss.monitors[1] on purpose, because one
laptop can drive different external displays and the geometry differs per
display.

It used to memoise the WHOLE id for the life of the process. So a display
change mid-run left the id pointing at the PREVIOUS display: geometry newly
measured on display B was filed under display A's key, and the next run on B
read A's calibration back. That is the exact failure the function exists to
prevent, arrived at from inside one process instead of across two machines,
and CLAUDE.md records the price — a view centre 27px out is "a systematic +8.5
degree bias on every bearing", with every internal consistency check passing.

window_reference.json is the sharpest case, because its value is a bare screen
rect with no secondary geometry key to catch the mismatch: a stale id makes
window_drift() compare display B's window against display A's reference and
call a window that never moved misplaced, and makes save_window_reference()
overwrite display A's reference with display B's rect.

THE HALF THAT IS EASY TO GET WRONG. Re-deriving on its own would be a WORSE
bug. _VIEW_CACHE is loaded once at import under the id current then, and
_save_view_cache() writes the whole in-memory dict under machine_id() as it
stands at save time — so a bare re-derive files display A's measured bounds
under display B's key, turning a wrong read that lasts one process into a
wrong calibration that lives on disk. The reload is not decoration; it is what
makes re-derivation safe, and it is checked end-to-end below.

AND WHY IT WARNS RATHER THAN RAISING. Five of the six callers of machine_id()
wrap it in `except Exception` and swallow it, so a raise would be
indistinguishable from doing nothing — the diagnosis-catalogue shape. That
asymmetry is measured here rather than asserted in prose.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import io
import json
import tempfile

import input_controller as ic

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


DISPLAY_A = "1728x1117"          # the laptop panel
DISPLAY_B = "3840x2160"          # an external monitor plugged in mid-run

_saved = {k: getattr(ic, k) for k in
          ("_MACHINE_ID", "_MACHINE_ID_DERIVED", "_MACHINE_HOST",
           "_VIEW_CACHE", "_VIEW_CACHE_FILE", "_WINDOW_REF_FILE",
           "_screen_geometry", "subprocess", "game_window_rect")}

_tmp = tempfile.mkdtemp()
_screen = {"now": DISPLAY_A}


def _reset(where):
    """Start from a clean process that has just booted on display `where`."""
    _screen["now"] = where
    ic._MACHINE_ID = None
    ic._MACHINE_ID_DERIVED = None
    ic._VIEW_CACHE = {}


try:
    ic._screen_geometry = lambda: _screen["now"]
    ic._VIEW_CACHE_FILE = os.path.join(_tmp, "view_bounds.json")
    ic._WINDOW_REF_FILE = os.path.join(_tmp, "window_reference.json")

    # --- 1. the change is NOTICED at all ----------------------------------
    _reset(DISPLAY_A)
    id_a = ic.machine_id()
    check("the id carries the display it was derived on",
          id_a.endswith("|" + DISPLAY_A))
    check("and is stable while nothing changes", ic.machine_id() == id_a)

    _screen["now"] = DISPLAY_B
    err = io.StringIO()
    _real_err, sys.stderr = sys.stderr, err
    try:
        id_b = ic.machine_id()
    finally:
        sys.stderr = _real_err
    check("plugging in a display CHANGES the id, it does not go stale",
          id_b != id_a)
    check("and the new id names the NEW display",
          id_b.endswith("|" + DISPLAY_B))
    check("only the display half moved; the machine half is unchanged",
          id_b.rsplit("|", 1)[0] == id_a.rsplit("|", 1)[0])

    # --- 2. it is not SILENT ----------------------------------------------
    warned = err.getvalue()
    check("the change is reported, not swallowed", warned.strip() != "")
    check("and the report names both ids, so the log says which is which",
          id_a in warned and id_b in warned)

    # --- 3. THE HAZARD RE-DERIVING WOULD OTHERWISE INTRODUCE ---------------
    # Display A measures its view bounds and saves them. Then the display
    # changes. Nothing measured on A may end up filed under B.
    _reset(DISPLAY_A)
    id_a = ic.machine_id()
    A_KEY, A_BOUNDS = (1728, 1117), (0, 1727, 67, 1116)
    ic._VIEW_CACHE[A_KEY] = A_BOUNDS
    ic._save_view_cache()

    _screen["now"] = DISPLAY_B
    _real_err, sys.stderr = sys.stderr, io.StringIO()
    try:
        id_b = ic.machine_id()
    finally:
        sys.stderr = _real_err
    check("the in-memory cache is dropped when the display changes, so the "
          "old display's bounds cannot be re-saved under the new id",
          A_KEY not in ic._VIEW_CACHE)

    # B now measures its own and saves. A's entry must not ride along.
    B_KEY, B_BOUNDS = (3840, 2160), (0, 3839, 120, 2159)
    ic._VIEW_CACHE[B_KEY] = B_BOUNDS
    ic._save_view_cache()
    on_disk = json.load(open(ic._VIEW_CACHE_FILE))
    b_bucket = on_disk.get(id_b, {})
    a_bucket = on_disk.get(id_a, {})
    check("display A's bounds were NOT written under display B's id",
          "1728,1117" not in b_bucket)
    check("display B's own measurement was stored", "3840,2160" in b_bucket)
    check("and display A's entry survived, so moving back still works",
          a_bucket.get("1728,1117") == list(A_BOUNDS))

    # --- 4. an id set BY HAND is still honoured ---------------------------
    # tests/routing/test_machine_cache.py fakes a second computer by assigning
    # _MACHINE_ID directly. An explicit override is a deliberate act, not
    # staleness, so re-derivation must not stamp on it.
    _reset(DISPLAY_A)
    ic.machine_id()
    ic._MACHINE_ID = "other-laptop|arm64|3840x2160"
    check("an explicitly assigned id is returned verbatim",
          ic.machine_id() == "other-laptop|arm64|3840x2160")
    ic._MACHINE_ID = None
    check("clearing it re-derives from the real display",
          ic.machine_id().endswith("|" + DISPLAY_A))

    # --- 5. the EXPENSIVE half is still memoised --------------------------
    # ioreg is a subprocess with a 5s timeout. Re-reading the display must not
    # drag it along, or every id check pays for a process spawn.
    class _Counting:
        def __init__(self, real):
            self._real, self.calls = real, 0

        def run(self, *a, **k):
            self.calls += 1
            return self._real.run(*a, **k)

        def __getattr__(self, n):
            return getattr(self._real, n)

    counting = _Counting(_saved["subprocess"])
    ic.subprocess = counting
    ic._MACHINE_HOST = None
    _reset(DISPLAY_A)
    _real_err, sys.stderr = sys.stderr, io.StringIO()
    try:
        for where in (DISPLAY_A, DISPLAY_B, DISPLAY_A, DISPLAY_B):
            _screen["now"] = where
            ic.machine_id()
    finally:
        sys.stderr = _real_err
    ic.subprocess = _saved["subprocess"]
    check("the hardware probe runs ONCE even across four re-derivations, "
          f"not once per call (ran {counting.calls}x)", counting.calls == 1)

    # --- 6. why it warns instead of raising -------------------------------
    # Measured, not assumed: the callers that swallow, and the one that does
    # not. A raise would be invisible in the swallowing ones.
    _reset(DISPLAY_A)
    ic.machine_id()
    json.dump({ic.machine_id(): [1.0, 2.0, 3.0, 4.0]},
              open(ic._WINDOW_REF_FILE, "w"))
    ic.game_window_rect = lambda: (1.0, 2.0, 3.0, 4.0)

    def _boom():
        raise RuntimeError("machine_id refused")

    real_mid = ic.machine_id
    swallowed, propagated = [], []
    ic.machine_id = _boom
    try:
        for name, call in (("_load_view_cache", lambda: ic._load_view_cache()),
                           ("_save_view_cache", lambda: ic._save_view_cache()),
                           ("_load_window_reference",
                            lambda: ic._load_window_reference()),
                           ("save_window_reference",
                            lambda: ic.save_window_reference())):
            try:
                call()
                swallowed.append(name)
            except RuntimeError:
                propagated.append(name)
    finally:
        ic.machine_id = real_mid
    check("the loaders/savers SWALLOW an exception from machine_id, which is "
          f"why raising would be silent (swallowed: {swallowed})",
          set(swallowed) == {"_load_view_cache", "_save_view_cache",
                             "_load_window_reference"})
    check("only save_window_reference would ever see a raise "
          f"(propagated: {propagated})",
          propagated == ["save_window_reference"])

    # --- 7. the REAL _screen_geometry re-probes; it does not memoise ------
    # Everything above fakes this seam, so the mechanism at the heart of the
    # fix would otherwise go unchecked: a cached mss reading puts the
    # staleness straight back one layer down.
    import types
    real_geom = _saved["_screen_geometry"]
    probes = {"n": 0}

    class _FakeSct:
        def __enter__(self):
            probes["n"] += 1
            return self

        def __exit__(self, *a):
            return False

        @property
        def monitors(self):
            w, h = _screen["now"].split("x")
            return [None, {"width": int(w), "height": int(h)}]

    fake_mss = types.ModuleType("mss")
    fake_mss.mss = _FakeSct
    real_mss, sys.modules["mss"] = sys.modules.get("mss"), fake_mss
    try:
        _screen["now"] = DISPLAY_A
        first = real_geom()
        _screen["now"] = DISPLAY_B
        second = real_geom()
    finally:
        if real_mss is None:
            sys.modules.pop("mss", None)
        else:
            sys.modules["mss"] = real_mss
    check("_screen_geometry reads the display FRESH on every call",
          (first, second) == (DISPLAY_A, DISPLAY_B) and probes["n"] == 2)

finally:
    for k, v in _saved.items():
        setattr(ic, k, v)
    for f in os.listdir(_tmp):
        os.remove(os.path.join(_tmp, f))
    os.rmdir(_tmp)

if FAILS:
    print(f"\n{len(FAILS)} FAILED")
    sys.exit(1)
print("\nall green")
