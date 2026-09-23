"""I-65 round 2: the deal gate must not release on an INCOMPLETE signature, and the
two new no-baseline call sites (match start after bans, half-change re-read) must not
need motion to release quickly when the hand is already there.

ROUND 1 WAS REFUTED. Its `_sig_unread_slots` treated any signature that was not
EXACTLY a 5-row tuple as "complete" -- meant to let test doubles like `("steady",)`
through, but it also waved through `()`, which is what `local_hand._read_ungated`
returns for an empty table and is the DOMINANT shape the gate actually polls
mid-deal (5733/6591 recorded frames, skeptic's s3_shapes.py). Its two new call sites
also required `seen` (an edge) to ever release, so an already-dealt static hand
waited the full 20s max_wait every time (skeptic's s4_stall.py).

Every signature used below is PRODUCTION-shaped: `()` (the ungated empty-table/short-
hand shape), a short tuple, or a real 5-tuple of (kind, digit, secondary, type) rows
with "unknown" rows mixed in -- never the old test's unrelated placeholder shapes.
"""
import io
import contextlib
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import orchestrator as o                                                # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


PLAYER_READ = ("player", 5, None, None)
PLAYER_UNREAD = ("player", None, None, None)
TACTICS_READ = ("tactics", None, None, "pitch_boost")
TACTICS_UNREAD = ("tactics", None, None, None)
UNKNOWN_ROW = ("unknown", None, None, None)
COMPLETE_SIG = tuple(PLAYER_READ for _ in range(5))

# ---- (a) _sig_unread_slots: shape and per-row completeness ---------------------------
check("() -- the dominant ungated mid-deal shape -- is fully UNREAD, not complete",
      o._sig_unread_slots(()) == [0, 1, 2, 3, 4], str(o._sig_unread_slots(())))
check("None is fully unread", o._sig_unread_slots(None) == [0, 1, 2, 3, 4])
check("a short tuple (ungated, short hand) is fully unread",
      o._sig_unread_slots((("unknown", None, None, None), ("unknown", None, None, None)))
      == [0, 1, 2, 3, 4])
check("a real 5-row, all read, is complete", o._sig_unread_slots(COMPLETE_SIG) == [])
check("a player row with no digit is unread at its own index",
      o._sig_unread_slots((PLAYER_READ,) * 4 + (PLAYER_UNREAD,)) == [4])
check("a tactics row with no type is unread at its own index",
      o._sig_unread_slots((PLAYER_READ,) * 3 + (TACTICS_READ, TACTICS_UNREAD)) == [4])
check("a tactics row WITH a type but no bonus is still complete (bonus not required)",
      o._sig_unread_slots((PLAYER_READ,) * 4 + (TACTICS_READ,)) == [])
check("an 'unknown' row is unread regardless of its other fields",
      o._sig_unread_slots((PLAYER_READ,) * 4 + (UNKNOWN_ROW,)) == [4])
if fails:
    print(f"\n{'FAILED: ' + ', '.join(fails)}")
    sys.exit(1)


# ---- fake-clock harness (same shape as the I-65 round-1 skeptic's s4_stall.py) -------
class _Clock:
    t = 1000.0

    def time(self):
        return self.t

    def sleep(self, s):
        self.t += s + 0.02

    def strftime(self, *a):
        return "x"

    def __getattr__(self, n):
        import time as _t
        return getattr(_t, n)


def drive(seq, no_motion_needed=False, baseline_present=True, max_wait=None,
          poll_interval=0.15, motion_seen=True):
    """Run the REAL wait_for_hand_deal against a fixed sequence of already-computed
    signatures (skips local_hand/PIL entirely -- this file tests the gate's decision
    logic, not the reader; that is test_readable_hand_gate.py's job and I-6x's).

    `motion_seen=False` simulates a screen where the delta NEVER crosses the motion
    threshold (a genuinely static hand, no play to trigger an edge) -- this is the
    real-world shape of the two no_motion_needed call sites, and the only way to
    prove no_motion_needed itself (not `_mean_abs_delta` always saying "moved") is
    what releases the gate.
    """
    c = _Clock()
    saved = (o.time, o._grab_settle_regions, o._mean_abs_delta, o._hand_signature,
              o.crop_gameplay_regions, o._fast_grab, o.reset_deal_frames,
              o.keep_deal_frame, o.log_deal_timing, o.record_observation)
    frames = iter(seq)
    state = {"sig": seq[0] if seq else ()}
    try:
        o.time = c
        o._grab_settle_regions = lambda names: {n: object() for n in names}
        o._mean_abs_delta = (lambda a, b: 999.0) if motion_seen else (lambda a, b: 0.0)
        o._hand_signature = lambda img: state["sig"]
        o.crop_gameplay_regions = lambda img: [("hand", object())]
        o._fast_grab = lambda: object()
        o.reset_deal_frames = lambda: None
        o.keep_deal_frame = lambda *a: None
        o.log_deal_timing = lambda row: None
        o.record_observation = lambda **k: None

        def advance(*_a, **_k):
            state["sig"] = next(frames, seq[-1] if seq else ())
        # advance the fed signature once per poll, driven from the sleep() call itself
        _orig_sleep = c.sleep
        def sleeping(s):
            _orig_sleep(s)
            advance()
        c.sleep = sleeping

        kwargs = dict(poll_interval=poll_interval, no_motion_needed=no_motion_needed,
                      baseline=(object() if baseline_present else None))
        if max_wait is not None:
            kwargs["max_wait"] = max_wait
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            released = o.wait_for_hand_deal(**kwargs)
        return released, c.t - 1000.0, buf.getvalue()
    finally:
        (o.time, o._grab_settle_regions, o._mean_abs_delta, o._hand_signature,
         o.crop_gameplay_regions, o._fast_grab, o.reset_deal_frames,
         o.keep_deal_frame, o.log_deal_timing, o.record_observation) = saved


# ---- (b) B: new call sites release FAST on an already-complete, stable hand,
#            with NO motion required -- motion_seen=False, so this can only release
#            through the no_motion_needed path, never through `seen` (kills a
#            "require motion at the new sites" mutant, which forces `seen` back into
#            the entry condition and would time out here instead of releasing).
released, dt, _out = drive([COMPLETE_SIG], no_motion_needed=True, motion_seen=False,
                           max_wait=3.0)
check("no_motion_needed releases on an already-complete static hand with NO "
      "motion ever seen", released is True, f"released={released}")
check("...within 1.0s of the fake clock (acceptance B)", dt <= 1.0, f"{dt:.2f}s")

# Control: the SAME static hand and lack of motion, WITHOUT no_motion_needed -- must
# NOT release at all (nothing ever sets `seen`, so it should time out).
released2, dt2, _ = drive([COMPLETE_SIG], no_motion_needed=False, motion_seen=False,
                          max_wait=1.0)
check("WITHOUT no_motion_needed and no motion, it does not release at all "
      "(proves the flag, not something else, is what releases it)",
      released2 is False, f"released={released2} after {dt2:.2f}s")

# ---- (c) A: an INCOMPLETE-but-stable signature never releases early -- only at
#            READABLE_HAND_BOUND ---------------------------------------------------
COVERED = (PLAYER_READ,) * 4 + (UNKNOWN_ROW,)     # one slot never reads -- stable, incomplete
released3, dt3, _ = drive([COVERED], no_motion_needed=False,
                          max_wait=o.READABLE_HAND_BOUND + 5.0)
check("a stable but INCOMPLETE signature does not release before the bound",
      released3 is True, f"released={released3}")
check("...and releases at the bound, not earlier (acceptance A: 0 early releases)",
      o.READABLE_HAND_BOUND - 0.01 <= dt3 <= o.READABLE_HAND_BOUND + 0.5,
      f"released at {dt3:.2f}s (bound {o.READABLE_HAND_BOUND}s)")

# ---- (d) C: a slot that NEVER reads (covered card) still releases -- nothing
#            blocks longer than the bound plus one poll --------------------------
released4, dt4, _ = drive([COVERED], no_motion_needed=True, motion_seen=False,
                          max_wait=o.READABLE_HAND_BOUND + 5.0, poll_interval=0.2)
check("a covered-card hand still releases (never stalls forever)",
      released4 is True, f"released={released4}")
check("...within bound + one poll_interval (acceptance C)",
      dt4 <= o.READABLE_HAND_BOUND + 0.2 + 0.05,
      f"released at {dt4:.2f}s (max allowed {o.READABLE_HAND_BOUND + 0.25:.2f}s)")

# () (the dominant ungated empty-table/still-animating shape) behaves the same way:
# stable (it repeats itself) but never complete, so it must hold to the bound too.
released5, dt5, _ = drive([()], no_motion_needed=True, motion_seen=False,
                          max_wait=o.READABLE_HAND_BOUND + 5.0)
check("a hand that reads () the whole time (still animating) holds to the bound, "
      "not 'complete' (this is what round 1 got wrong)",
      released5 is True and dt5 >= o.READABLE_HAND_BOUND - 0.01,
      f"released={released5} at {dt5:.2f}s")

# ---- (e) a real deal: incomplete while animating, complete once it lands --------
ANIMATING_1 = ()
ANIMATING_2 = (("unknown", None, None, None),)
released6, dt6, _ = drive([ANIMATING_1, ANIMATING_1, ANIMATING_2, ANIMATING_2,
                           COMPLETE_SIG, COMPLETE_SIG, COMPLETE_SIG],
                          no_motion_needed=True, poll_interval=0.05)
check("a hand that animates then completes releases once complete AND stable "
      "(not on the earlier animating-but-stable-twice reads)",
      released6 is True and dt6 < o.READABLE_HAND_BOUND, f"released at {dt6:.2f}s")

# ---- (f) structural: the half-change and match-start call sites exist -----------
# CONTIGUOUS substrings, not "somewhere before" (an rfind-anywhere-before check
# would find the OTHER call site's identical text and pass even after one of the
# two gates was deleted -- caught by running this exact check against the M4/M5
# mutants below before trusting it).
_src = open(os.path.join(_ROOT, "orchestrator.py")).read()
_half_block = ('wait_for_hand_deal(no_motion_needed=True)\n'
               '                            state_json = '
               'read_state_for_turn(turns_this_half=_hint)')
check("a bare wait_for_hand_deal(no_motion_needed=True) call sits immediately "
      "before the half-change state re-read",
      _half_block in _src)

_ban_block = ('wait_for_hand_deal(no_motion_needed=True)\n'
              '                wait_for_screen_to_settle(max_wait=8.0, regions="ban")')
check("a bare wait_for_hand_deal(no_motion_needed=True) call sits immediately "
      "before the ban screen's own settle wait (the match's first hand read)",
      _ban_block in _src)

print(f"\n{'FAILED: ' + ', '.join(fails) if fails else 'all checks passed'}")
sys.exit(1 if fails else 0)
