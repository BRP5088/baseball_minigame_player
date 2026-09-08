"""patch45: STOP_LOOK_YAW ships ON.

THE A/B (2026-09-08 07:07-07:52, commit a411fe4, `--arms off,on --flag
STOP_LOOK_YAW --trials 20`, 10 a side interleaved; overnight/
chain_trials_ab_stop_yaw.*; agent_progress/closed-loop/review/
ab_stop_yaw_score.out):

    arm    arrived   walk median   129 looked   first credible dx after the stop
    off     9/10       78.3 s          5         median -352  [-383 -361 -352 -302 -264]
    on      9/10       79.4 s          5         median  +72  [ -96  -86  +72  +77 +150]

Arrival is a tie at n=10 (Fisher p = 1.0; each arm's one loss was a wanderer
hazard the stop never saw: the tables-aisle patron, the NPC at the top of the
stairs). THE INSTRUMENT is not a tie: after the capped 0.3 s strafe the scene
still sits ~350 px LEFT of the walking heading on every off-arm trial, and
after the yaw it sits within ~90 px on every on-arm trial -- two populations
that do not overlap at 5 and 5. That is the sensor confirming the mechanism
on each firing, which is what the flag was built to be measured on. Ships
True; the OFF path stays as the control, tested at False explicitly.
"""
import ast, os, sys
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
C = os.path.join(ROOT, "chain_walk.py"); T = os.path.join(ROOT, "tests", "routing", "test_chain_walk.py")
c = open(C).read(); t = open(T).read()
if "STOP_LOOK_YAW = True" in c:
    raise SystemExit("ALREADY APPLIED")
edits_c = [
 ("""# the character. `stop_yaw` carries it until the next turn-only stop.
STOP_LOOK_YAW = False
""",
  """# the character. `stop_yaw` carries it until the next turn-only stop.
#
# SHIPS ON (patch45, 2026-09-08 07:55). The A/B, 10 a side interleaved
# (overnight/chain_trials_ab_stop_yaw.*): arrival 9/10 against 9/10, and the
# INSTRUMENT -- the first credible fit's dx after a looked 129 stop -- read
# median -352 px on every off-arm trial (the strafe left the scene ~18 deg
# left) and median +72 px on every on-arm trial (five yaws of -12.6..-22.9
# deg): two populations, no overlap at 5 and 5. The OFF path is the control
# and its test sets the flag False for itself.
STOP_LOOK_YAW = True
"""),
]
edits_t = [
 ("""    def test_the_flag_ships_OFF_and_reuses_the_END_TURNs_own_constants(self):
        # Literals (10.11): a test that reads the constant it guards passes
        # forever. STOP_LOOK_YAW invents no number of its own.
        self.assertIs(chain_walk.STOP_LOOK_YAW, False)
""",
  """    def test_the_flag_ships_ON_and_reuses_the_END_TURNs_own_constants(self):
        # Literals (10.11): a test that reads the constant it guards passes
        # forever. STOP_LOOK_YAW invents no number of its own. It ships ON
        # (patch45): the A/B's instrument read the first credible dx after a
        # looked 129 stop at median -352 px with the strafe (off, 5 of 5) and
        # +72 px with the yaw (on, 5 of 5), arrival 9/10 each.
        self.assertIs(chain_walk.STOP_LOOK_YAW, True)
"""),
 ("""    def test_with_the_flag_OFF_the_stop_STRAFES_exactly_as_today(self):
        # THE CONTROL, and the shipped path. Pinned as literals so a mutant
        # that yaws regardless of the flag fails here, and so that "the flag
        # off is byte-for-byte today's behaviour" is a measurement.
        self.assertIs(chain_walk.STOP_LOOK_YAW, False)
""",
  """    def test_with_the_flag_OFF_the_stop_STRAFES_exactly_as_today(self):
        # THE CONTROL (the A/B's off arm; no longer the shipped path since
        # patch45). Pinned as literals so a mutant that yaws regardless of
        # the flag fails here, and so that "the flag off is byte-for-byte the
        # old behaviour" stays a measurement.
        prev = chain_walk.STOP_LOOK_YAW
        chain_walk.STOP_LOOK_YAW = False
        self.addCleanup(setattr, chain_walk, "STOP_LOOK_YAW", prev)
"""),
]
# three look-around tests pin the STRAFE path's exact turn list: they are the control now
OFF = ("        prev = chain_walk.STOP_LOOK_YAW\n        chain_walk.STOP_LOOK_YAW = False\n"
       "        self.addCleanup(setattr, chain_walk, \"STOP_LOOK_YAW\", prev)\n")
for name in ("test_an_unverified_stop_looks_left_and_right_before_giving_up",
             "test_a_strong_first_look_ends_the_look_around",
             "test_a_weak_first_look_still_samples_the_other_side"):
    line = f"    def {name}(self):\n"
    assert t.count(line) == 1, ("control test", name, t.count(line))
    edits_t.append((line, line + OFF))
for a, b in edits_c: assert c.count(a) == 1, ("chain_walk anchor", a[:50], c.count(a))
for a, b in edits_t: assert t.count(a) == 1, ("test anchor", a[:50], t.count(a))
for a, b in edits_c: c = c.replace(a, b)
for a, b in edits_t: t = t.replace(a, b)
ast.parse(c); ast.parse(t)
open(C, "w").write(c); open(T, "w").write(t); print("patch45 applied to", ROOT)
