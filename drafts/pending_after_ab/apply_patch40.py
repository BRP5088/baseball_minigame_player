"""patch40: at_table() accepts a correlation of at least MATCH_MIN_WITH_WORD
(0.20) when the OCR reads at least one prompt word.

Two walks tonight stood at the prompt with "Baseball Cards [] Play ($50)"
plainly on screen and were scored FAILED: ab4 trial 10 (three iterations,
scores 0.229-0.237) and b11 trial 10 (three iterations, 0.220-0.226), all
under MATCH_MIN 0.25 in dark captures (mean 63-75). Measured on EVERY route
frame on disk (7,885 frames at k < 185, overnight/census/
at_table_raw_scores_20260908.json): the raw score alone does not separate
(negatives reach 0.218; the misses are 0.220-0.237, one population), but
every negative scoring 0.17 or more reads 0 prompt words except one at 0.189
(1 word), while the sub-threshold prompt frames read 1-3 words. The
conjunction score >= 0.20 AND ocr_words >= 1 fires on 0 of 7,885 route frames
and recovers 16 of the 24 prompt frames under 0.25, including all six misses.
Usage: python apply_patch40.py [ROOT].
"""
import os, sys
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
P = os.path.join(ROOT, "table_prompt.py"); T = os.path.join(ROOT, "tests", "routing", "test_at_table_ocr_path.py")
p = open(P).read(); t = open(T).read()
if "MATCH_MIN_WITH_WORD" in p:
    raise SystemExit("ALREADY APPLIED")
edits_p = [
 ('''MATCH_MIN = 0.25           # stroke-shape correlation
''', '''MATCH_MIN = 0.25           # stroke-shape correlation
# A correlation this high is believed when the OCR also reads at least ONE
# prompt word. Two arrivals on 2026-09-08 were scored failed with the prompt
# plainly on screen at 0.220-0.237 (dark captures). Over all 7,885 route
# frames on disk the score alone overlaps (negatives reach 0.218) but every
# negative at or above 0.17 reads 0 prompt words, one excepted at 0.189, while
# the missed prompts read 1-3: the conjunction fires on 0 route frames and
# recovers 16 of the 24 prompt frames under MATCH_MIN.
MATCH_MIN_WITH_WORD = 0.20
'''),
 ('''    if score(img) >= MATCH_MIN:
        return True
    return ocr_says_prompt(img)
''', '''    s = score(img)
    if s >= MATCH_MIN:
        return True
    words = ocr_words(img)
    if words >= OCR_MIN_WORDS:
        return True
    return s >= MATCH_MIN_WITH_WORD and words >= 1
'''),
]
edits_t = [
 ('''    def test_wanda_prompt_stays_rejected_without_the_ink_gate(self):
''', '''    def test_a_dark_prompt_is_seen_by_the_correlation_plus_one_word(self):
        # b11 trial 10, it064: the prompt on screen, score 0.226 (under
        # MATCH_MIN), one OCR word. Pinned: neither the mask alone nor the OCR
        # alone accepts it, the conjunction does.
        im = Image.open(os.path.join(CASES, "prompt_dark_b11_t10_it064.jpg")).convert("RGB")
        self.assertEqual(tp.MATCH_MIN_WITH_WORD, 0.20)
        self.assertLess(tp.score(im), tp.MATCH_MIN)
        self.assertGreaterEqual(tp.score(im), 0.20)
        self.assertEqual(tp.ocr_words(im), 1)
        self.assertTrue(tp.at_table(im))

    def test_the_top_route_negatives_stay_rejected(self):
        # The two highest-scoring non-prompt frames of 7,885 (0.218, 0.216:
        # zero words) and the one negative with a prompt word (0.189, under
        # MATCH_MIN_WITH_WORD): all three stay False.
        for name in ("no_prompt_top_negative_k173.jpg", "no_prompt_top_negative_k89.jpg", "no_prompt_one_word_0189.jpg"):
            im = Image.open(os.path.join(CASES, name)).convert("RGB")
            self.assertFalse(tp.at_table(im), name)
        im = Image.open(os.path.join(CASES, "no_prompt_one_word_0189.jpg")).convert("RGB")
        self.assertGreaterEqual(tp.ocr_words(im), 1, "the fixture must carry a word, or the threshold is untested")
        self.assertLess(tp.score(im), tp.MATCH_MIN_WITH_WORD)

    def test_wanda_prompt_stays_rejected_without_the_ink_gate(self):
'''),
]
for a, b in edits_p: assert p.count(a) == 1, ("table_prompt anchor", p.count(a))
for a, b in edits_t: assert t.count(a) == 1, ("test anchor", t.count(a))
for a, b in edits_p: p = p.replace(a, b)
for a, b in edits_t: t = t.replace(a, b)
open(P, "w").write(p); open(T, "w").write(t); print("patch40 applied to", ROOT)
