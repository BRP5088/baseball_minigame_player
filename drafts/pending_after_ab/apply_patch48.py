"""patch48 (harness only): a MISSING GAME WINDOW makes the run WAIT, not burn trials.

2026-09-08 10:30 and 10:36: chiaki's game window went off screen twice
(input_controller.game_window_rect lists ON-SCREEN windows only, so a Space
switch or a fullscreen app in front of chiaki makes it None). Each time the
child raised NoGameWindow inside reset_environment within a second, the
parent scored INVALID and moved to the next trial number, and the fit-gate
A/B's 20-trial budget was spent as 12 INVALID rows in ~15 s; the relaunch lost
five more the same way. INVALID never counts as a failure, but a burnt trial
number is a trial not run.

Now: the child waits up to WINDOW_WAIT_SEC (120) for a window before its reset;
the parent re-runs an INVALID trial number up to WINDOW_RETRY_MAX (2) times
after waiting for the window, keeping the INVALID row (marked `window_retry`)
so nothing is hidden. Pure helpers, read at call time (§10.18), tested
offline with stubbed probe/clock.
"""
import ast, os, sys
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
C = os.path.join(ROOT, "overnight", "chain_trials.py"); T = os.path.join(ROOT, "tests", "routing", "test_chain_walk.py")
c = open(C).read(); t = open(T).read()
if "WINDOW_RETRY_MAX" in c:
    raise SystemExit("ALREADY APPLIED")
edits_c = [
 ("""CEILING = int(TIME_CAP + SETUP_BUDGET)   # 580 — the external kill
""",
  """CEILING = int(TIME_CAP + SETUP_BUDGET)   # 580 — the external kill
# A MISSING GAME WINDOW is not a trial result (patch48). game_window_rect()
# lists ON-SCREEN windows only, so a Space switch or a fullscreen app in front
# of chiaki makes it None; the child then dies in reset_environment within a
# second and the parent scored INVALID and moved on -- 12 of an A/B's 20
# trial numbers went that way in ~15 s on 2026-09-08. The child now waits for
# the window before its reset; the parent re-runs an INVALID number after
# waiting, a bounded number of times, keeping the INVALID row marked.
WINDOW_WAIT_SEC = 120.0
WINDOW_POLL_SEC = 3.0
WINDOW_RETRY_MAX = 2


def wait_for_game_window(log, probe=None, sleep=time.sleep, clock=time.monotonic,
                         max_sec=None):
    \"\"\"True once a chiaki game window is on screen, False after max_sec.\"\"\"
    if probe is None:
        import input_controller
        probe = input_controller.game_window_rect
    if max_sec is None:
        max_sec = WINDOW_WAIT_SEC
    t0 = clock()
    waited = False
    while True:
        if probe() is not None:
            if waited:
                log(f"  chiaki game window back after {clock() - t0:.0f}s")
            return True
        if clock() - t0 >= max_sec:
            log(f"  no chiaki game window on screen for {max_sec:.0f}s")
            return False
        if not waited:
            log(f"  no chiaki game window on screen (another Space, a fullscreen "
                f"app in front, or the stream reconnecting); waiting up to "
                f"{max_sec:.0f}s")
            waited = True
        sleep(WINDOW_POLL_SEC)


def retry_this_trial(outcome, retries):
    \"\"\"Re-run an INVALID trial number, at most WINDOW_RETRY_MAX times.\"\"\"
    return outcome == INVALID and retries < WINDOW_RETRY_MAX
"""),
 ("""    reset_env.reset_environment(log=log, progress_file="progress_testing.json")
    time.sleep(1.2)               # the world has to finish appearing
""",
  """    if not wait_for_game_window(log):
        raise SystemExit(f"no chiaki game window for {WINDOW_WAIT_SEC:.0f}s")
    reset_env.reset_environment(log=log, progress_file="progress_testing.json")
    time.sleep(1.2)               # the world has to finish appearing
"""),
 ("""        for i in range(1, trials + 1):
            # The child inherits this environment, so the journal path reaches
""",
  """        i = 1
        window_retries = 0
        while i <= trials:
            # The child inherits this environment, so the journal path reaches
"""),
 ("""            if row.get("timeout_diagnosis"):
                log(f"     {row['timeout_diagnosis']}")
            _harness.save_result(OUT, res)
""",
  """            if row.get("timeout_diagnosis"):
                log(f"     {row['timeout_diagnosis']}")
            _harness.save_result(OUT, res)
            if retry_this_trial(outcome, window_retries):
                window_retries += 1
                row["window_retry"] = window_retries
                log(f"     INVALID: waiting for the game window, then re-running "
                    f"trial {i} ({window_retries}/{WINDOW_RETRY_MAX})")
                wait_for_game_window(log)
                _harness.save_result(OUT, res)
                continue
            window_retries = 0
            i += 1
"""),
]
edits_t = [
 ("""    def test_the_default_arms_ROW_LABEL_is_still_pan(self):
""",
  """    def test_wait_for_game_window_returns_when_the_probe_finds_one(self):
        # patch48: the probe is None twice (off screen), then a rect; a stub
        # clock and sleep make it instant. Three probes, True, no give-up line.
        answers = [None, None, (0, 0, 100, 100)]
        calls = []
        t = [0.0]
        def probe(): calls.append(1); return answers.pop(0)
        def sleep(s): t[0] += s
        ok = chain_trials.wait_for_game_window(self.log, probe=probe, sleep=sleep,
                                                clock=lambda: t[0], max_sec=120.0)
        self.assertTrue(ok)
        self.assertEqual(len(calls), 3)
        self.assertTrue(any("waiting up to 120s" in m for m in self.logs), self.logs)
        self.assertTrue(any("window back after" in m for m in self.logs), self.logs)

    def test_wait_for_game_window_gives_up_after_the_budget(self):
        t = [0.0]
        def sleep(s): t[0] += s
        ok = chain_trials.wait_for_game_window(self.log, probe=lambda: None, sleep=sleep,
                                                clock=lambda: t[0], max_sec=10.0)
        self.assertFalse(ok)
        self.assertGreaterEqual(t[0], 9.0, "it waited out the budget, not one poll")
        self.assertTrue(any("for 10s" in m for m in self.logs), self.logs)

    def test_an_INVALID_trial_number_is_re_run_at_most_WINDOW_RETRY_MAX_times(self):
        # Literals (10.11): INVALID re-runs twice, a third INVALID moves on,
        # and a real result never re-runs.
        self.assertEqual(chain_trials.WINDOW_RETRY_MAX, 2)
        self.assertTrue(chain_trials.retry_this_trial(chain_trials.INVALID, 0))
        self.assertTrue(chain_trials.retry_this_trial(chain_trials.INVALID, 1))
        self.assertFalse(chain_trials.retry_this_trial(chain_trials.INVALID, 2))
        for oc in (chain_trials.ARRIVED, chain_trials.FAILED, chain_trials.TIMED_OUT):
            self.assertFalse(chain_trials.retry_this_trial(oc, 0), oc)

    def test_the_default_arms_ROW_LABEL_is_still_pan(self):
"""),
]
for a, b in edits_c: assert c.count(a) == 1, ("chain_trials anchor", a[:60], c.count(a))
for a, b in edits_t: assert t.count(a) == 1, ("test anchor", a[:60], t.count(a))
for a, b in edits_c: c = c.replace(a, b)
for a, b in edits_t: t = t.replace(a, b)
ast.parse(c); ast.parse(t)
open(C, "w").write(c); open(T, "w").write(t); print("patch48 applied to", ROOT)
