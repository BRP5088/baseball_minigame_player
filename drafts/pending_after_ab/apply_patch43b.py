"""patch43b (applies AFTER apply_patch43.py): the LOST rescue's looks search the
WHOLE chain behind the last credible sighting, not six waypoints behind it.

b16 trial 19 (agent_progress/closed-loop/review/notes_b16_t19.md): the
character walked into the photographer NPC at chain 112-114; a WIDE
relocalisation then matched k=136 on 191 inliers -- WRONG (the frames at the
next stop match chain 0120) -- and `last_cred_k` became 136 while the truth
was ~120. patch43's window, [last_cred_k - 7, last_cred_k + 54], would have
searched [129, 190] and could never have found the character. The estimate
when a walk is lost is not merely "a little ahead": a wrong wide fit puts
the last credible k 15-35 waypoints past the truth (reloc_past_129_census:
jumps from 109-114 to 131-144). No lookback constant is derivable from that;
the honest window is everything from the chain's start to last_cred_k +
WIDE_AHEAD. The wrong-place census maxed at 164 inliers against the strong
gate of 165, and the trial is already lost, so the wider search costs a few
seconds on a walk that was over.
"""
import ast, os, sys
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
C = os.path.join(ROOT, "chain_walk.py"); T = os.path.join(ROOT, "tests", "routing", "test_chain_walk.py")
c = open(C).read(); t = open(T).read()
if "LOST_RESCUE_LOOKBACK = None" in c:
    raise SystemExit("ALREADY APPLIED")
if "LOST_RESCUE_LOOKBACK = 6" not in c:
    raise SystemExit("apply_patch43.py first")
edits_c = [
 ("LOST_RESCUE_LOOKBACK = 6\n",
  "# None = the WHOLE chain behind the last credible k (patch43b). b16 t19: a\n"
  "# wrong 191-inlier wide relocalisation made last_cred_k 136 while the\n"
  "# character stood at ~120; a six-waypoint lookback could never find it.\n"
  "LOST_RESCUE_LOOKBACK = None\n"),
 ("                start = max(last_cred_k - LOST_RESCUE_LOOKBACK, 0)\n",
  "                start = (0 if LOST_RESCUE_LOOKBACK is None\n"
  "                         else max(last_cred_k - LOST_RESCUE_LOOKBACK, 0))\n"
  "                span = max(last_cred_k + WIDE_AHEAD - start, WIDE_AHEAD)\n"),
 ("                    f2 = chain.locate(img2, start, window=WIDE_AHEAD)\n",
  "                    f2 = chain.locate(img2, start, window=span)\n"),
]
edits_t = [
 ("        self.at_hint = {h: list(v) for h, v in (at_hint or {}).items()}\n",
  "        self.at_hint = {h: list(v) for h, v in (at_hint or {}).items()}\n"
  "        self.wide_windows = []\n"),
 ("            self.wide_calls.append(k_hint)\n            queued = self.at_hint.get(k_hint)\n",
  "            self.wide_calls.append(k_hint)\n            self.wide_windows.append(window)\n            queued = self.at_hint.get(k_hint)\n"),
 ("        self.assertEqual(chain_walk.LOST_RESCUE_LOOKBACK, 6)\n",
  "        self.assertIsNone(chain_walk.LOST_RESCUE_LOOKBACK, \"the whole chain behind (patch43b)\")\n"),
 ("""        # THE POINT OF THE RUNG. The last credible sighting was waypoint 10;
        # blind advances carried k to 16. The three looks must be hinted at
        # 10 - 6 = 4 — the ground the character may actually be standing on —
        # and NOT at k, which is where the plan thinks it is.
        ch = self.chain(at_hint={4: [Fix(k=13, inliers=120),
                                     Fix(k=13, inliers=120),
                                     Fix(k=13, inliers=170)]})
""",
  """        # THE POINT OF THE RUNG. The last credible sighting was waypoint 10;
        # blind advances carried k to 16. The three looks must search the WHOLE
        # chain behind that sighting (hint 0, patch43b: b16 t19's last credible
        # k was a wrong wide fit 16 waypoints past the truth) out to
        # last_cred_k + WIDE_AHEAD -- and NOT around k, where the plan thinks
        # it is.
        ch = self.chain(at_hint={0: [Fix(k=13, inliers=120),
                                     Fix(k=13, inliers=120),
                                     Fix(k=13, inliers=170)]})
"""),
 ("""        self.assertEqual(ch.wide_calls[-3:], [4, 4, 4],
                         "the three looks are hinted at last_cred_k - 6")
        self.assertNotIn(4, ch.wide_calls[:-3],
                         "and nothing else in this walk asked there")
""",
  """        self.assertEqual(ch.wide_calls[-3:], [0, 0, 0],
                         "the three looks search from the chain's start")
        self.assertEqual(ch.wide_windows[-3:], [10 + chain_walk.WIDE_AHEAD] * 3,
                         "out to last_cred_k + WIDE_AHEAD")
        self.assertNotIn(0, ch.wide_calls[:-3],
                         "and nothing else in this walk asked there")
"""),
]
for a, b in edits_c: assert c.count(a) == 1, ("chain_walk anchor", a.split("\n")[0][:60], c.count(a))
for a, b in edits_t: assert t.count(a) == 1, ("test anchor", a.split("\n")[0][:60], t.count(a))
# every rescue test scripts the fake sensor's wide answers by HINT; the hint is now 0
import re
n_hint = len(re.findall(r"at_hint=\{\d+: \[", t))
assert n_hint >= 7, ("at_hint anchors", n_hint)
for a, b in edits_c: c = c.replace(a, b)
for a, b in edits_t: t = t.replace(a, b)
t = re.sub(r"at_hint=\{\d+: \[", "at_hint={0: [", t)
assert len(re.findall(r"at_hint=\{[1-9]\d*: \[", t)) == 0
ast.parse(c); ast.parse(t)
open(C, "w").write(c); open(T, "w").write(t); print("patch43b applied to", ROOT)
