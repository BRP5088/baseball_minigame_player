"""patch42 (2026-09-08, after batch 15): the rewind ships DISABLED, and
at_table() gains the "$50" fee token as a last OCR path.

PART 1 -- STOP_REWIND_MAX 2 -> 0.

Rule C of patch41 (an unverified turn stop REWINDS to the last credible k and
re-approaches) was measured live at the one stop the audit's table named as
the lever, the bar-entrance stop at chain 129:

    batches 12-14 (rule C absent): trials that took 129 UNVERIFIED  11/11 arrived
    batch 15      (rule C live):   trials that REWOUND at 129        0/3  arrived,
                                   each lost at k=109 on the re-approach

The b15 trial 4 reader (agent_progress/closed-loop/review/
notes_cur_t04_1788853535.md): the character is face-to-chest with an NPC at
the turn point; turn-back and turn-wait find nothing; the rewind walks it
BACK along the same line into the same NPC, every action on the re-approach
is unevidenced so the once-per-blockage turn-early never re-arms, and the
walk goes miss/escape/lost at a k BEHIND the stop -- on ground it had
already crossed. Advancing unverified there, which is what the 11/11 did,
puts the blockage behind the character and lets the next push resolve it.

Rules A and B (a thin fit at a stop is nothing; a retry needs evidence of
being short) are unchanged and their tests untouched. The rewind MECHANISM
stays in the code with its tests, which now set the budget to 2 for
themselves (`_rewind_budget(self, 2)`), and one new test pins the shipped 0
with the census above.

PART 2 -- the fee token.

Three batch-13 trial-5 arrivals stood at the dealer's prompt (dark frame,
"Baseball Cards [] Play ($50)" plainly on screen) and were scored FAILED:
score 0.147 under MATCH_MIN_WITH_WORD (0.20) with one OCR word. Measured over
every route frame on disk (overnight/census/at_table_ocr_tokens_20260908.json,
scratchpad ocr_token_census.py; band (0.30, 0.58, 0.72, 0.70), 3x, PSM 6,
both polarities):

    "$50" / "(50)" read on route frames (k < 185)     0 of 7,885
    read on the known prompt frames                    58 of 81
    the three b13 t5 frames                            3 of 3

Zero false positives on the whole negative corpus is the bar §3 sets for the
$50 gate, and the token is the safest addition on record: the prompt words
at >= 1 read on 24 negatives, the fee on none. It runs LAST, only when the
mask, the two-word rule and the word-plus-score rule have all said no, on the
census band exactly (not TEXT_BOX -- the measurement is for that band).
"""
import ast
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
C = os.path.join(ROOT, "chain_walk.py")
T = os.path.join(ROOT, "tests", "routing", "test_chain_walk.py")
P = os.path.join(ROOT, "table_prompt.py")
Q = os.path.join(ROOT, "tests", "routing", "test_at_table_ocr_path.py")
c = open(C).read(); t = open(T).read(); p = open(P).read(); q = open(Q).read()
if "\nSTOP_REWIND_MAX = 0\n" in c or "ocr_reads_fee" in p:
    raise SystemExit("ALREADY APPLIED")

# ---------------------------------------------------------------- chain_walk
edits_c = [
 ('''\nSTOP_REWIND_MAX = 2\n''',
  '''\n# SHIPPED AT ZERO (2026-09-08, batch 15). Measured at the bar-entrance stop
# 129: batches 12-14 took it UNVERIFIED and arrived 11/11; batch 15 REWOUND
# there 3 times and arrived 0/3, each lost at 109 on the re-approach -- the
# rewind walks the character back into the NPC it had just met, and every
# action on a re-approach is unevidenced so turn-early never re-arms (b15 t4,
# agent_progress/closed-loop/review/notes_cur_t04_1788853535.md). The
# mechanism stays; its tests run it at 2 for themselves.
STOP_REWIND_MAX = 0
'''),
]

# ------------------------------------------------------------ test_chain_walk
HELPER = '''import chain_walk
import pose


def _rewind_budget(tc, n):
    """The rewind MECHANISM's tests run at the budget they were written for.

    STOP_REWIND_MAX ships at 0 (see chain_walk.py and
    test_the_rewind_ships_DISABLED_...). Every test that exercises a rewind, or
    asserts that a rewind did NOT happen for a reason other than the budget,
    sets 2 here first, so it still tests the rule it names.
    """
    prev = chain_walk.STOP_REWIND_MAX
    chain_walk.STOP_REWIND_MAX = n
    tc.addCleanup(setattr, chain_walk, "STOP_REWIND_MAX", prev)
'''
edits_t = [
 ('''import chain_walk
import pose
''', HELPER),
 ('''        self.assertEqual(chain_walk.STOP_REWIND_MAX, 2)
        wps = [Wp(0, 90.0)]
''',
  '''        # (the budget is set to 2 above; the shipped value is 0, pinned below)
        wps = [Wp(0, 90.0)]
'''),
 ('''    def test_no_retry_pushes_at_a_stop_after_a_wall_scale_fit(self):
''',
  '''    def test_the_rewind_ships_DISABLED_an_unverified_stop_is_taken_on_the_first_pass(self):
        # SHIPPED AT ZERO (2026-09-08, batch 15). Rule C's rewind was measured
        # live at the bar-entrance stop 129, the stop the audit's table named
        # as the lever: across batches 12-14 a trial that took 129 UNVERIFIED
        # (no rewind) arrived 11 of 11; in batch 15 the three trials that
        # REWOUND there arrived 0 of 3, each lost at 109 on the re-approach.
        # The rewind walks the character back along the same line into the
        # NPC it had just met, and every action on the re-approach is
        # unevidenced so the once-per-blockage turn-early never re-arms (b15
        # trial 4, notes_cur_t04_1788853535.md). Rules A and B are unchanged;
        # the mechanism stays and the tests above run it at 2 on purpose.
        #
        # Same walk as the test above, at the SHIPPED budget: after the back
        # and the wait the stop is taken unverified on the FIRST pass, and no
        # row carries `rewound_to`.
        self.assertEqual(chain_walk.STOP_REWIND_MAX, 0)
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate([(90.0, -0.35)] * 8 + [(0.0, 0.0)]
                                    + [(0.0, -0.35)] * 4, start=1):
            w = Wp(i, h); w.lx = 0.0; w.ly = ly; wps.append(w)
        ch = FakeChain(14, [Fix(k=1)], default=None, lookback=None)
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = rig.go(time_cap=400.0)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:6], [
            "advanced", "blind-advance", "blind-advance",
            "turn-back", "turn-wait", "turned-unverified"], acts)
        self.assertEqual(res["fixes"][5]["k"], 9,
                         "the stop is taken unverified on the first pass")
        self.assertEqual([f for f in res["fixes"] if "rewound_to" in f], [],
                         "no rewind at the shipped budget")

    def test_no_retry_pushes_at_a_stop_after_a_wall_scale_fit(self):
'''),
]

# Every test method whose body mentions the rewind gets the budget it was
# written under, as its first statement (after a docstring, if any).
tree = ast.parse(t)
lines = t.split("\n")
inserts = []
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
        seg = ast.get_source_segment(t, node) or ""
        if "rewound_to" in seg or "STOP_REWIND_MAX" in seg:
            first = node.body[0]
            after = first.end_lineno if (isinstance(first, ast.Expr)
                                         and isinstance(first.value, ast.Constant)
                                         and isinstance(first.value.value, str)) else node.lineno
            indent = " " * (node.col_offset + 4)
            inserts.append((after, indent))
names = sorted(n.name for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
               and ("rewound_to" in (ast.get_source_segment(t, n) or "")
                    or "STOP_REWIND_MAX" in (ast.get_source_segment(t, n) or "")))
EXPECTED = [
 "test_a_fit_at_exactly_WEAK_MIN_INLIERS_is_not_nothing_at_a_stop",
 "test_a_past_acceptance_advances_and_never_rewinds",
 "test_a_relocalisation_is_the_rewind_floor_b11_trial_12",
 "test_a_rewind_never_falls_back_past_a_stop_that_verified",
 "test_a_rewind_re_approaches_on_the_ORDINARY_blind_budget",
 "test_a_stop_is_advanced_unverified_only_after_STOP_REWIND_MAX_rewinds",
 "test_after_an_unverified_turn_blind_pushes_are_capped_at_two",
 "test_an_unverified_stop_rewinds_to_the_last_credible_k_and_re_approaches",
 "test_the_rewind_budget_is_spent_PER_STOP_not_per_walk",
]
assert names == EXPECTED, ("rewind tests found", names)

# ---------------------------------------------------------------- table_prompt
edits_p = [
 ('''import glob
import os
''', '''import glob
import os
import re
'''),
 ('''    s = score(img)
    if s >= MATCH_MIN:
        return True
    words = ocr_words(img)
    if words >= OCR_MIN_WORDS:
        return True
    return s >= MATCH_MIN_WITH_WORD and words >= 1
''',
  '''    s = score(img)
    if s >= MATCH_MIN:
        return True
    words = ocr_words(img)
    if words >= OCR_MIN_WORDS:
        return True
    if s >= MATCH_MIN_WITH_WORD and words >= 1:
        return True
    return ocr_reads_fee(img)
'''),
 ('''def ocr_says_prompt(img):
    return ocr_words(img) >= OCR_MIN_WORDS
''',
  '''def ocr_says_prompt(img):
    return ocr_words(img) >= OCR_MIN_WORDS


# THE FEE TOKEN, "$50" / "(50)", IS THE SAFEST ADDITION ON RECORD (2026-09-08).
# Three batch-13 trial-5 arrivals stood at the prompt on a dark frame and were
# scored FAILED: score 0.147 under MATCH_MIN_WITH_WORD with one word. Measured
# over EVERY route frame on disk, 3x, PSM 6, both polarities, on FEE_BOX
# (overnight/census/at_table_ocr_tokens_20260908.json):
#
#     "$50" or "(50)" read on route frames (k < 185)    0 of 7,885
#     read on the known prompt frames                   58 of 81
#     prompt WORDS >= 1 on the same route frames        24 of 7,885
#
# So it runs LAST, only after the mask, the two-word rule and the
# word-plus-score rule have all said no, and it reads the census band exactly
# -- FEE_BOX is not TEXT_BOX, and the zero was measured on FEE_BOX.
FEE_BOX = (0.30, 0.58, 0.72, 0.70)
FEE_UPSCALE = 3
_FEE_RE = re.compile(r"\\$ ?50|\\(\\s*\\$?\\s*5\\s*0\\s*\\)|50\\)|\\(50")


def ocr_reads_fee(img):
    """Does the prompt band read the fee, "$50" or "(50)", in either polarity?"""
    from PIL import ImageOps
    import ocr_glyphs
    w, h = img.size
    x0, y0, x1, y1 = FEE_BOX
    c = img.convert("L").crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))
    c = c.resize((c.width * FEE_UPSCALE, c.height * FEE_UPSCALE), Image.BICUBIC)
    for cand in (c, ImageOps.invert(c)):
        txt = (ocr_glyphs.image_to_text(cand, OCR_PSM, None) or "").lower()
        if _FEE_RE.search(txt):
            return True
    return False
'''),
]

# ------------------------------------------------------- test_at_table_ocr_path
edits_q = [
 ('''    def test_two_words_are_required(self):
''',
  '''    def test_the_fee_token_is_seen_when_the_mask_and_the_words_are_not(self):
        # b13 trial 5, it073 (overnight/chain_frames/t1788848574793): the
        # character at the dealer's prompt on a dark frame, scored FAILED --
        # score 0.147 under MATCH_MIN_WITH_WORD, one OCR word. The fee token
        # "$50" reads on 0 of 7,885 route frames and on this one (census
        # overnight/census/at_table_ocr_tokens_20260908.json). Pinned: neither
        # earlier path accepts it, the fee path does.
        im = Image.open(os.path.join(CASES, "prompt_dark_b13_t05_it073.jpg")).convert("RGB")
        self.assertEqual(tp.FEE_BOX, (0.30, 0.58, 0.72, 0.70), "the census band")
        self.assertLess(tp.score(im), tp.MATCH_MIN_WITH_WORD)
        self.assertLess(tp.ocr_words(im), tp.OCR_MIN_WORDS)
        self.assertTrue(tp.ocr_reads_fee(im))
        self.assertTrue(tp.at_table(im))

    def test_the_fee_token_reads_on_no_negative_fixture(self):
        # Every negative this file knows, plus Wanda: the fee path must be as
        # silent on them as the census says it is on the whole route.
        names = [os.path.join(CASES, n) for n in (
            "no_prompt_top_negative_k173.jpg", "no_prompt_top_negative_k89.jpg",
            "no_prompt_one_word_0189.jpg")]
        names += [QUEST_LOG, CLEAN_BAR]
        names += [os.path.join(_ROOT, "test_fixtures", "wanda_prompt", n)
                  for n in ("wanda_ref.jpg", "wanda_occluded.jpg")]
        for path in names:
            self.assertFalse(tp.ocr_reads_fee(load(path)), path)
            self.assertFalse(tp.at_table(load(path)), path)

    def test_two_words_are_required(self):
'''),
]

# ------------------------------------------------ every anchor, before any write
for a, b in edits_c: assert c.count(a) == 1, ("chain_walk anchor", a.split("\n")[1][:70], c.count(a))
for a, b in edits_t: assert t.count(a) == 1, ("test anchor", a.split("\n")[0][:70], t.count(a))
for a, b in edits_p: assert p.count(a) == 1, ("table_prompt anchor", a.split("\n")[0][:70], p.count(a))
for a, b in edits_q: assert q.count(a) == 1, ("ocr test anchor", a.split("\n")[0][:70], q.count(a))
assert os.path.isfile(os.path.join(ROOT, "test_fixtures", "table_prompt_cases",
                                   "prompt_dark_b13_t05_it073.jpg")), "fixture missing"
assert len(inserts) == len(EXPECTED), (len(inserts), len(EXPECTED))

# line insertions first (bottom-up, so earlier line numbers stay valid), then
# the string edits, whose anchors do not span an inserted line
for after, indent in sorted(inserts, reverse=True):
    lines.insert(after, f"{indent}_rewind_budget(self, 2)")
t = "\n".join(lines)
for a, b in edits_c: c = c.replace(a, b)
for a, b in edits_t: t = t.replace(a, b)
for a, b in edits_p: p = p.replace(a, b)
for a, b in edits_q: q = q.replace(a, b)
ast.parse(c); ast.parse(t); ast.parse(p); ast.parse(q)
open(C, "w").write(c); open(T, "w").write(t); open(P, "w").write(p); open(Q, "w").write(q)
print("patch42 applied to", ROOT, "| rewind tests given budget 2:", len(inserts))
