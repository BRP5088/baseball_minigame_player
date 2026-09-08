"""patch50: DOOR_STOP_EXTRA_PUSH ships ON.

THE A/B (2026-09-08 11:06-11:48, `--arms off,on --flag DOOR_STOP_EXTRA_PUSH
--trials 20`, 10 a side interleaved; overnight/chain_trials_ab_doorstep.*):

    arm   arrived   the 39 stop verified by            inliers   fit scale
    off    9/10     looked 3, aligned 6, UNVERIFIED 1    38       0.96 [0.80..1.05]
    on    10/10     head-on 10 (turned 3, aligned 7)     66       1.04 [1.01..1.11]

One extra push along the corridor before the stairs turn (the user's
observation from the stream): no on-arm trial needed the look-around, the
stop's inliers nearly doubled, and the short-of-the-door scale tail is
gone. The off arm's one loss was an unverified 39 at scale 0.80.
"""
import ast, os, sys
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
C = os.path.join(ROOT, "chain_walk.py"); T = os.path.join(ROOT, "tests", "routing", "test_chain_walk.py")
c = open(C).read(); t = open(T).read()
if "DOOR_STOP_EXTRA_PUSH = True" in c:
    raise SystemExit("ALREADY APPLIED")
edits_c = [("\nDOOR_STOP_EXTRA_PUSH = False\n",
            "\n# SHIPS ON (patch50, 2026-09-08 11:50): the A/B, 10 a side -- on arm 10/10, the\n"
            "# 39 stop verified HEAD-ON on every trial at 66 inliers, fit scale 1.04\n"
            "# [1.01..1.11]; off arm 9/10, three look-arounds and one unverified loss, 38\n"
            "# inliers, scale 0.96 [0.80..1.05] (overnight/chain_trials_ab_doorstep.*).\n"
            "DOOR_STOP_EXTRA_PUSH = True\n")]
edits_t = [("    def test_the_flag_ships_OFF_and_the_index_is_this_chains_door_stop(self):\n",
            "    def test_the_flag_ships_ON_and_the_index_is_this_chains_door_stop(self):\n"),
           ("        self.assertIs(chain_walk.DOOR_STOP_EXTRA_PUSH, False)\n",
            "        # ON since patch50: the A/B's on arm verified the door stop head-on 10 of\n"
            "        # 10 at scale 1.04 against the off arm's 0.96 with a 0.80 tail.\n"
            "        self.assertIs(chain_walk.DOOR_STOP_EXTRA_PUSH, True)\n")]
for a, b in edits_c: assert c.count(a) == 1, ("chain_walk anchor", a[:50], c.count(a))
for a, b in edits_t: assert t.count(a) == 1, ("test anchor", a[:50], t.count(a))
for a, b in edits_c: c = c.replace(a, b)
for a, b in edits_t: t = t.replace(a, b)
ast.parse(c); ast.parse(t)
open(C, "w").write(c); open(T, "w").write(t); print("patch50 applied to", ROOT)
