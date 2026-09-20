"""I-02: a cursor that goes blind ONE STEP FROM ITS TARGET must be probed, not refused.

_walk_cursor_to returned False the instant cursor_slot read None mid-walk, and the
glow window is structurally blind at slot 4 (CLAUDE.md 10.35: "slot 4 never exceeds
11.0 at ANY offset, while slots 0-3 read 26-28"). So a walk TOWARD slot 4 can land
there and then refuse forever -- slot 4 could never be a play or discard TARGET.
`tests/rig/test_blind_cursor_nudges_off.py` fixed the case where the cursor cannot
be located AT ALL before any move; this file is the mid-walk case, where the walk
has just pressed toward the target and the last known position was one step away.

THE PROBE USES SELECTION, NOT GLOW. `agent_progress/cursor-lift-refutation/` measured
that hovering alone lifts nothing (slot 4 reads -10.0 hovered or not); only
SELECTING a card lifts it, ~44px, unambiguous. So `_probe_select_blind_target`
presses select_card once and reads `selected_cards`' lift instead of guessing.

WHAT THIS FILE PINS:
  (a) the probe selects the TARGET when the cursor really is there, and the walk
      succeeds with the target already selected (no second press needed);
  (b) the probe can land on a DIFFERENT slot (the cursor was really elsewhere); that
      slot is explicitly untoggled via _deselect_verified -- not incidentally cleared
      by some other press -- and the walk continues to reach the target from its
      true position;
  (c) if _deselect_verified reports the untoggle did NOT land, the call refuses
      rather than trusting it and leaving a stray card selected;
  (d) a target row the lift reader cannot see (CAUTION 2 from the refutation:
      selected_cards abstains on a fallback y) is refused WITHOUT pressing
      select_card at all -- there is nothing to trust a "nothing lifted" answer
      against;
  (e) a probe that never lifts ANYTHING (every select_card press is swallowed or
      lands on nothing) is bounded by PROBE_SELECT_MAX, not retried forever;
  CONTROL: a cursor lost somewhere that is NOT one step from the target still hits
      the OLD refusal, unprobed -- otherwise this fix is indistinguishable from
      probing on every lost cursor, which is not what was asked for or measured.

(b) and (c) mock `_deselect_verified` rather than modelling its toggle through the
fake screen. A first version of this file let the fake screen's OWN toggle
semantics put the wrong slot back down as a side effect of a later probe attempt --
so a mutant that deleted the untoggle call entirely still passed, because the next
probe's own select_card press happened to consume the same pre-scripted lift and
looked identical from the outside. Mocking the call directly is what tells "the
code called _deselect_verified" apart from "the board ended up looking right by
coincidence."
"""
import os as _os
import sys as _sys

_os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
_os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import input_controller as ic                                        # noqa: E402

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


N = ic.MAX_HAND_SIZE
REST = [200, 160, 150, 165, 220]


class ProbeScreen:
    """A 5-slot fan whose GLOW and SELECTION are driven independently.

    `cur_glow_slot` is where move_left/move_right leave the cursor, for the
    purpose of the glow reading -- a slot in `blind` never glows above the gate
    even when the cursor is genuinely sitting on it (the slot-4 case).
    `select_queue` is what each successive select_card press actually lifts (or,
    if already up, puts back down) -- decoupled from `cur_glow_slot` so a test can
    say "the probe reveals the cursor was really somewhere else" without having to
    fake WHY, only THAT. An exhausted queue means every further select_card press
    is silently dropped (models a dead reader / swallowed press).
    `unreadable` marks rows the LIFT reader (not the glow reader) cannot see --
    ys[i] is None there, exactly as a fallback-y row reads in production.
    """

    def __init__(self, cur_glow_slot, blind=frozenset(), unreadable=frozenset(),
                 select_queue=()):
        self.cur_glow_slot = cur_glow_slot
        self.blind = set(blind)
        self.unreadable = set(unreadable)
        self.select_queue = list(select_queue)
        self.y = list(REST)
        self.sent = []

    def selected(self):
        return [i for i, y in enumerate(self.y) if REST[i] - y >= 25]

    def _ys(self):
        return [None if i in self.unreadable else 100 for i in range(N)]

    def look(self):
        glow = [0.2] * N
        if self.cur_glow_slot is not None and self.cur_glow_slot not in self.blind:
            glow[self.cur_glow_slot] = 27.0
        return glow, self._ys(), N, self.selected()

    def press(self, key):
        self.sent.append(key)
        if key == "move_left":
            self.cur_glow_slot = max(0, (self.cur_glow_slot or 0) - 1)
        elif key == "move_right":
            self.cur_glow_slot = min(N - 1, (self.cur_glow_slot or 0) + 1)
        elif key == "select_card":
            if not self.select_queue:
                return                      # every further press is swallowed
            t = self.select_queue.pop(0)
            if REST[t] - self.y[t] >= 25:
                self.y[t] = REST[t]         # already up -> DOWN
            else:
                self.y[t] -= 44             # a selected card RISES


_real_press = ic.press
_real_deselect = ic._deselect_verified
try:
    # --- (a) the probe selects the target when the cursor really is there ------
    s = ProbeScreen(cur_glow_slot=2, blind={4}, select_queue=[4])
    ic.press = s.press
    ok, sel = ic._walk_cursor_to(4, s.look)
    check(ok is True, f"walking onto a structurally blind target must succeed via "
          f"the probe; got {ok!r}")
    check(4 in sel, f"the target must be SELECTED after the probe, so the caller's "
          f"_select_verified commits nothing further; sel={sel!r}")
    check("select_card" in s.sent,
          f"the probe must have pressed select_card; pressed {s.sent!r}")

    # --- (b) the probe lands on a DIFFERENT slot; it is EXPLICITLY untoggled via
    #         _deselect_verified and the walk continues to the real target -------
    s = ProbeScreen(cur_glow_slot=2, blind={4}, select_queue=[3, 4])
    ic.press = s.press
    deselect_calls = []

    def fake_deselect_ok(slot, look):
        deselect_calls.append(slot)
        # Put it back down on the fake screen so the walk's own re-reads stay
        # consistent -- WITHOUT going through select_card, so a mutant that
        # deletes this call has no other press left to accidentally fix things.
        if REST[slot] - s.y[slot] >= 25:
            s.y[slot] = REST[slot]
        return True, s.selected()

    ic._deselect_verified = fake_deselect_ok
    try:
        ok, sel = ic._walk_cursor_to(4, s.look)
    finally:
        ic._deselect_verified = _real_deselect
    check(ok is True,
          f"a probe landing on the wrong slot must still end in success once the "
          f"walk continues from the true position; got {ok!r}")
    check(deselect_calls == [3],
          f"the wrong slot must be untoggled by an EXPLICIT call to "
          f"_deselect_verified, not incidentally cleared some other way; "
          f"calls={deselect_calls!r}")
    check(4 in sel and 3 not in sel,
          f"the target must end up selected and the wrong slot must be down; "
          f"sel={sel!r}")

    # --- (c) _deselect_verified reports FAILURE: refuse, do not trust it --------
    # select_queue carries a SECOND entry (4) on purpose: if the code ignores ok2
    # and presses on, the walk continues, probes again, and select_card genuinely
    # lifts the target -- which would make the whole call return True with slot 3
    # STILL stray-lifted underneath it. That is what "ignore ok2" actually costs,
    # and it is the only way to tell it apart from a probe that fails on its own
    # merits (a version of this file whose queue stopped at [3] let a downstream
    # probe fail for an unrelated reason and passed with the check unverified).
    s = ProbeScreen(cur_glow_slot=2, blind={4}, select_queue=[3, 4])
    ic.press = s.press
    deselect_calls = []

    def fake_deselect_fail(slot, look):
        deselect_calls.append(slot)
        return False, [3]              # the untoggle did NOT land

    ic._deselect_verified = fake_deselect_fail
    try:
        ok, sel = ic._walk_cursor_to(4, s.look)
    finally:
        ic._deselect_verified = _real_deselect
    check(ok is False,
          f"an untoggle _deselect_verified reports as FAILED must refuse rather "
          f"than proceed as if it landed -- even though a later probe would "
          f"otherwise go on to find the target; got {ok!r}")
    check(deselect_calls == [3],
          f"the untoggle must actually be ATTEMPTED before refusing, not skipped; "
          f"calls={deselect_calls!r}")
    check(3 in sel,
          f"the returned selection must still show the stray lifted, proving this "
          f"is a REFUSAL and not a silent commit; sel={sel!r}")
    check(s.sent.count("select_card") == 1,
          f"the walk must refuse on the FIRST probe's failed untoggle and never "
          f"even reach a second probe -- exactly one select_card press (the "
          f"initial probe's own discovery press; the untoggle itself is mocked "
          f"and presses nothing); got {s.sent.count('select_card')} in {s.sent!r}")

    # --- (d) target row unseen by the lift reader: refuse, press NOTHING --------
    s = ProbeScreen(cur_glow_slot=2, blind={4}, unreadable={4}, select_queue=[4])
    ic.press = s.press
    ok, sel = ic._walk_cursor_to(4, s.look)
    check(ok is False,
          f"a target row the lift reader cannot see must refuse; got {ok!r}")
    check("select_card" not in s.sent,
          f"and it must refuse WITHOUT pressing select_card at all -- there is "
          f"nothing to trust a 'nothing lifted' answer against here; "
          f"pressed {s.sent!r}")

    # --- (e) nothing EVER lifts: bounded by PROBE_SELECT_MAX, not open-ended ----
    s = ProbeScreen(cur_glow_slot=2, blind={4}, select_queue=[])   # every press dead
    ic.press = s.press
    ok, sel = ic._walk_cursor_to(4, s.look)
    check(ok is False,
          f"a probe that never lifts anything must refuse; got {ok!r}")
    check(s.sent.count("select_card") == ic.PROBE_SELECT_MAX,
          f"the probe must stop at PROBE_SELECT_MAX ({ic.PROBE_SELECT_MAX}) "
          f"select_card presses, not fewer or more: got "
          f"{s.sent.count('select_card')}")

    # --- CONTROL: a cursor lost somewhere NOT one step from the target still
    #              hits the OLD refusal, unprobed ------------------------------
    s = ProbeScreen(cur_glow_slot=0, blind={2}, select_queue=[2])
    ic.press = s.press
    ok, sel = ic._walk_cursor_to(4, s.look)
    check(ok is False,
          f"CONTROL: losing the cursor two slots from the target must still refuse "
          f"the old way; got {ok!r}")
    check("select_card" not in s.sent,
          f"CONTROL: and must NOT probe -- the mechanism is scoped to 'one step "
          f"from the target', not every lost cursor; pressed {s.sent!r}")

    # --- the constant is a literal, not a re-derivation of itself (CLAUDE.md 10.11) --
    check(ic.PROBE_SELECT_MAX == 2,
          f"PROBE_SELECT_MAX is {ic.PROBE_SELECT_MAX}, not 2. It is derived from "
          "the 15.20% clustered press-drop rate (one retry absorbs a lone drop); "
          "moving it needs that derivation redone.")
finally:
    ic.press = _real_press
    ic._deselect_verified = _real_deselect

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  a blind-slot target is probed by selection, a wrong probe is explicitly "
      "untoggled and the walk continues, a reported-failed untoggle refuses, an "
      "unseen target row refuses without pressing, a dead probe stays bounded, "
      "and a cursor lost elsewhere still hits the old refusal unprobed")
