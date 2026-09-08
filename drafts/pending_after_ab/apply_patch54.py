"""patch54: SETTLE PROBE -- sample the fit WHILE the character is coming to rest.

WHY. A closed-loop iteration is a median 1.44 s. 400 ms is stick, 59 ms is the
whole of perception, and 700 ms is two hard-coded 0.35 s sleeps: SETTLE_SEC in
`walk_leg` (:95) and a bare literal inside `turn_to`'s loop (:191), the second
paid on 80.5% of pushes. Nothing has ever measured whether 0.35 s is needed.

WHY A STANDALONE PROBE COULD NOT DO IT. `tools/settle_response.py` turns, pushes
and samples on its own, and it cannot keep the character on the route: without
the controller's lateral corrections, blind handling and escapes it stalls
within a few pushes, the anchor freezes, and 8 of 96 readings clear the
credibility floor. Measured twice, once through the screen and once through the
frame dump, same result. The instrument has to ride a REAL walk.

WHY IT NEEDS A CALLBACK RATHER THAN SAMPLING AFTER THE PUSH. `walk_leg` sleeps
SETTLE_SEC before it returns, so anything sampling from its return starts 350 ms
after the stick released and misses the entire window. `on_release` is invoked
the instant the stick is zeroed and BEFORE that sleep.

WHAT CHANGES WHEN IT IS OFF: nothing. `on_release` defaults to None and the two
lines around it are untouched, so the shipped path is byte-for-byte today's.
The probe is read from the environment at CALL time, never at import (10.18,
and the import-time BASEBALL_TEST_RUN incident that silently dropped every
stick send for a whole run).

WHAT IT COSTS WHEN ON: the callback spends up to SETTLE_PROBE_DELAYS[-1] seconds
sampling, ON TOP of the settle that still follows, so a probe walk is slower
than a real one. That is why it is a separate short run and never an arm of a
measured batch.

Applies to: slow_traverse.py, chain_walk.py, tests/routing/test_chain_walk.py.
Run:  .venv/bin/python -B drafts/pending_after_ab/apply_patch54.py [ROOT]
"""
import ast
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
S = os.path.join(ROOT, "slow_traverse.py")
C = os.path.join(ROOT, "chain_walk.py")
T = os.path.join(ROOT, "tests", "routing", "test_chain_walk.py")
s = open(S).read()
c = open(C).read()
t = open(T).read()

edits_s = [
 ('''def walk_leg(lx, ly, seconds, capture, read_heading, label="", log=print,
             step_sec=None):''',
  '''def walk_leg(lx, ly, seconds, capture, read_heading, label="", log=print,
             step_sec=None, on_release=None):'''),
 ('''        ar.send(["left_x 0", "left_y 0"])
        time.sleep(SETTLE_SEC)
''',
  '''        ar.send(["left_x 0", "left_y 0"])
        # THE INSTANT THE STICK IS ZEROED, before the settle. Anything hooked
        # after this function returns starts SETTLE_SEC late and cannot see the
        # window it exists to measure (patch54). Default None: the two lines
        # around this are the shipped path, untouched.
        if on_release is not None:
            on_release()
        time.sleep(SETTLE_SEC)
'''),
]

edits_c = [
 # the constants, beside the other probe-ish knobs
 ('''PUSH_SEC = 0.40                 # the duration that table was measured at''',
  '''PUSH_SEC = 0.40                 # the duration that table was measured at
# SETTLE PROBE (patch54), OFF unless BASEBALL_SETTLE_PROBE is set in the
# environment. After each push it captures and fits at these delays measured
# FROM THE STICK RELEASE, and writes the inlier counts into the journal row, so
# a real walk -- with the controller keeping the character on the route -- says
# whether SETTLE_SEC's 0.35 s is needed. It makes the walk slower, so it is a
# separate short run, never an arm of a measured batch.
SETTLE_PROBE_ENV = "BASEBALL_SETTLE_PROBE"
SETTLE_PROBE_DELAYS = (0.00, 0.05, 0.10, 0.15, 0.25, 0.35)'''),
 # the reader, at CALL time
 ('''def _last_stop_index(plan):''',
  '''def settle_probe_on(env=None):
    """Is the settle probe armed? Read at CALL time, never at import (10.18).

    A module-level knob captured in a default cannot be redirected by a test or
    a harness, and this project has the scar: `tools/prompt_ocr_ab` set
    BASEBALL_TEST_RUN at import and every stick send for the rest of that live
    run was silently dropped.
    """
    e = os.environ if env is None else env
    return bool(e.get(SETTLE_PROBE_ENV))


def _last_stop_index(plan):'''),
 # the sampler and the push site
 ('''        if do_push:
            push(PUSH_MAG, PUSH_SEC)
            res["pushes"] += 1
''',
  '''        settle_rows = None       # this iteration's probe samples, if armed
        if do_push:
            probe = None
            if settle_probe_on():
                probe = []

                def _sample(_k=k, _probe=probe):
                    t0 = time.monotonic()
                    for d in SETTLE_PROBE_DELAYS:
                        while time.monotonic() - t0 < d:
                            time.sleep(0.005)
                        im = capture()
                        f = chain.locate(im, _k, window=WINDOW) if im is not None else None
                        _probe.append({"delay": d,
                                       "inliers": None if f is None else f.inliers,
                                       "k": None if f is None else f.k})

                push(PUSH_MAG, PUSH_SEC, on_release=_sample)
            else:
                push(PUSH_MAG, PUSH_SEC)
            settle_rows = probe          # attached to this iteration's row
            res["pushes"] += 1
'''),
 # push() must forward the callback
 # the row carries what the probe saw, or the key is absent entirely
 ('''        row = {"iteration": iteration, "k": k, "target": target_k,
               "fix": _fix_row(fix), "action": action, "lateral": lateral,
               "at_end": at_end,''',
  '''        row = {"iteration": iteration, "k": k, "target": target_k,
               "fix": _fix_row(fix), "action": action, "lateral": lateral,
               "at_end": at_end,
               **({"settle": settle_rows} if settle_rows else {}),'''),
 ('''            return _st.walk_leg(0.0, -abs(mag), secs, capture, read_heading,
                                label="chain push", log=log, step_sec=secs)''',
  '''            # Forwarded ONLY when there is one, so the shipped call is the
            # call it has always been -- four tests stub walk_leg with today's
            # signature, and passing on_release=None to them is a TypeError.
            extra = {} if on_release is None else {"on_release": on_release}
            return _st.walk_leg(0.0, -abs(mag), secs, capture, read_heading,
                                label="chain push", log=log, step_sec=secs,
                                **extra)'''),
 ('''        def push(mag, secs, _st=st):''',
  '''        def push(mag, secs, on_release=None, _st=st):'''),
]

NEW_TESTS = '''
class SettleProbe(unittest.TestCase):
    """patch54: the fit sampled WHILE the character is still coming to rest.

    700 ms of a 1440 ms iteration is two hard-coded 0.35 s sleeps and neither
    has ever been measured. A standalone probe cannot do it -- without the
    controller the character leaves the route within a few pushes and 8 of 96
    readings clear the credibility floor -- so the sampler rides a real walk.
    It is OFF unless the environment says otherwise, and off it changes nothing.
    """

    def test_the_probe_is_read_at_CALL_time_and_defaults_OFF(self):
        # 10.18: a knob captured in a default cannot be redirected, and the
        # import-time BASEBALL_TEST_RUN incident dropped every stick send of a
        # live run. Drive both answers through an injected environment.
        self.assertFalse(chain_walk.settle_probe_on({}))
        self.assertTrue(chain_walk.settle_probe_on(
            {chain_walk.SETTLE_PROBE_ENV: "1"}))
        self.assertEqual(chain_walk.SETTLE_PROBE_ENV, "BASEBALL_SETTLE_PROBE")
        self.assertNotIn(chain_walk.SETTLE_PROBE_ENV, os.environ,
                         "ANTI-VACUITY: the suite must not run with it armed")

    def test_walk_leg_calls_on_release_AFTER_zeroing_and_BEFORE_the_settle(self):
        # The whole point: a hook that fires after walk_leg returns starts
        # SETTLE_SEC late and misses the window. Order is the assertion.
        import slow_traverse as st
        from PIL import Image
        shot = Image.new("RGB", (8, 8))      # walk_leg greys every capture
        order = []
        real_send, real_sleep = st.ar.send, st.time.sleep
        st.ar.send = lambda lines: order.append(("send", tuple(lines)))
        st.time.sleep = lambda s: order.append(("sleep", round(s, 3)))
        try:
            st.walk_leg(0.0, -0.45, 0.40, lambda: shot, lambda: 0.0,
                        log=lambda *a: None, step_sec=0.40,
                        on_release=lambda: order.append(("PROBE",)))
        finally:
            st.ar.send, st.time.sleep = real_send, real_sleep
        kinds = [o[0] for o in order]
        self.assertIn("PROBE", kinds, "the callback never fired")
        zeroed = next(i for i, o in enumerate(order)
                      if o[0] == "send" and "left_x 0" in o[1])
        probe = kinds.index("PROBE")
        settle = next(i for i, o in enumerate(order)
                      if o[0] == "sleep" and o[1] == round(st.SETTLE_SEC, 3)
                      and i > zeroed)
        self.assertLess(zeroed, probe, "it must fire AFTER the stick is zeroed")
        self.assertLess(probe, settle, "...and BEFORE the settle sleep")

    def test_with_no_callback_walk_leg_is_byte_for_byte_todays_path(self):
        # The shipped path must not gain a branch's worth of behaviour.
        import slow_traverse as st
        from PIL import Image
        shot = Image.new("RGB", (8, 8))      # walk_leg greys every capture
        order = []
        real_send, real_sleep = st.ar.send, st.time.sleep
        st.ar.send = lambda lines: order.append(("send", tuple(lines)))
        st.time.sleep = lambda s: order.append(("sleep", round(s, 3)))
        try:
            st.walk_leg(0.0, -0.45, 0.40, lambda: shot, lambda: 0.0,
                        log=lambda *a: None, step_sec=0.40)
        finally:
            st.ar.send, st.time.sleep = real_send, real_sleep
        self.assertEqual([o[0] for o in order],
                         ["send", "sleep", "send", "sleep"],
                         "push, wait, zero, settle -- and nothing else")
        self.assertEqual(order[1], ("sleep", 0.4))
        self.assertEqual(order[3], ("sleep", round(st.SETTLE_SEC, 3)))

'''

edits_t = [
 ("class StopLookYaw(unittest.TestCase):", NEW_TESTS + "\nclass StopLookYaw(unittest.TestCase):"),
]

# ------------------------------------------- assert EVERYTHING, then write
for a, b in edits_s:
    assert s.count(a) == 1, ("slow_traverse anchor", a[:50], s.count(a))
for a, b in edits_c:
    assert c.count(a) == 1, ("chain_walk anchor", a[:50], c.count(a))
for a, b in edits_t:
    assert t.count(a) == 1, ("test anchor", a[:50], t.count(a))
assert "on_release" not in s and "SETTLE_PROBE" not in c
assert "class SettleProbe" not in t
assert c.count("import os") == 1, "the probe reads os.environ"
assert c.count("import time") == 1
# the settle itself is NOT touched
assert s.count("        time.sleep(SETTLE_SEC)\n") == 1
assert s.count("SETTLE_SEC = 0.35") == 1

for a, b in edits_s:
    s = s.replace(a, b)
for a, b in edits_c:
    c = c.replace(a, b)
for a, b in edits_t:
    t = t.replace(a, b)

ast.parse(s)
ast.parse(c)
ast.parse(t)
assert s.count("on_release=None") == 1
assert s.count("if on_release is not None:") == 1
assert s.count("        time.sleep(SETTLE_SEC)\n") == 1, "the settle must be untouched"
assert s.count("SETTLE_SEC = 0.35") == 1
assert c.count("def settle_probe_on(") == 1
assert c.count("settle_rows = None") == 1
assert c.count('**({"settle": settle_rows} if settle_rows else {}),') == 1
assert c.count("on_release=_sample") == 1
assert c.count('extra = {} if on_release is None else') == 1
# THREE push sites existed (10.10: count before trusting a match). One gained
# the probe branch, which keeps a plain call in its else, so the plain string
# still appears three times and the probing call is its own string.
assert c.count("push(PUSH_MAG, PUSH_SEC)") == 3, c.count("push(PUSH_MAG, PUSH_SEC)")
assert t.count("class SettleProbe(unittest.TestCase):") == 1

open(S, "w").write(s)
open(C, "w").write(c)
open(T, "w").write(t)
print("patch54 applied to", ROOT)
