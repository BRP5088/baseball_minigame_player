"""table_prompt: OCR as a SECOND path in at_table(). APPLY ONLY WHEN NO LIVE RUN IMPORTS table_prompt.
Also writes tests/routing/test_at_table_ocr_path.py. Then run that test and
tests/routing/test_at_table_threshold.py, and mutation-test (see README)."""
p = "table_prompt.py"; s = open(p).read()
def rep(old, new):
    global s
    assert s.count(old) == 1, (s.count(old), old[:60]); s = s.replace(old, new)

rep('''    if _raw_patch(img).std() < MIN_CONTRAST:
        return False
    return ink(img) >= INK_MIN and score(img) >= MATCH_MIN
''', '''    if _raw_patch(img).std() < MIN_CONTRAST:
        return False
    if ink(img) >= INK_MIN and score(img) >= MATCH_MIN:
        return True
    return ocr_says_prompt(img)


# THE STROKE MASK CANNOT SEE WHITE TEXT OVER A BRIGHT BACKGROUND, BY
# CONSTRUCTION. It keeps a pixel only if it is > STROKE_BRIGHT and its 11x11
# neighbourhood averages < STROKE_LOCAL -- the rule that removes the dealer's
# white face -- so the prompt over the LIGHT TABLE TOP (camera pitched down
# after walking into the table; goal-leg A/B trial 1, 2026-09-07, score -0.001,
# ink 0.0001) and the prompt over the DEALER'S BODY (demos/dealer_circle, 26
# frames) both score under MATCH_MIN with the prompt plainly on screen.
# Local-contrast masks were measured over 3,937 frames and refused: no delta
# clears the gate on the bright-table frame, and every delta loses old
# positives or admits new ones (tools/prompt_mask_ab.py).
#
# OCR is a different instrument. Measured over the same corpora plus 43
# table-leg end frames (tools/prompt_ocr_ab.py, overnight/census/prompt_ocr_ab.json):
#
#     words >= 2      recall on the 1289 frames the mask accepts   341   (26%)
#                     false positives on 693 frames at non-table nodes   0
#                     the quest-log false-positive anchor               0 words
#                     route frames the mask rejects                 26 hits, all
#                       dealer_circle frames whose OCR text reads the prompt
#
# So it is strictly an ADDITION: the mask stays first and OCR runs only when the
# mask says no. It is scale-sensitive (the recorded anchor reads one word at 3x
# and four at 2x or 4x), which is why its recall alone is poor and why it must
# never replace the mask. tesserocr is main-thread-only (CLAUDE.md §3); at_table
# is called from the main thread everywhere in production.
OCR_UPSCALE = 3
OCR_PSM = 6              # block mode; PSM 7 read nothing on the anchors
OCR_FUZZ = 0.75          # "Basehal" / "Candsy" on the bright-table frame
OCR_MIN_WORDS = 2        # of baseball / cards / play; 0 false positives at 2
OCR_WORDS = ("baseball", "cards", "play")


def ocr_words(img):
    """How many of OCR_WORDS the prompt band reads, over both polarities."""
    import difflib
    import re
    from PIL import ImageOps
    import ocr_glyphs
    w, h = img.size
    x0, y0, x1, y1 = TEXT_BOX
    c = img.convert("L").crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))
    c = c.resize((c.width * OCR_UPSCALE, c.height * OCR_UPSCALE), Image.BICUBIC)
    best = 0
    for cand in (c, ImageOps.invert(c)):
        txt = ocr_glyphs.image_to_text(cand, OCR_PSM, None) or ""
        toks = re.sub(r"[^a-z0-9$() ]+", " ", txt.lower().replace("|", " ")).split()
        hits = sum(1 for wanted in OCR_WORDS
                   if any(difflib.SequenceMatcher(None, wanted, t).ratio() >= OCR_FUZZ
                          for t in toks))
        best = max(best, hits)
    return best


def ocr_says_prompt(img):
    return ocr_words(img) >= OCR_MIN_WORDS
''')
open(p, "w").write(s); print("patched table_prompt.py")

open("tests/routing/test_at_table_ocr_path.py", "w").write('''"""at_table() reads the prompt over a BRIGHT background through OCR, and only there.

Two real frames the stroke mask scores as absent with the prompt plainly on
screen (see the comment above ocr_words in table_prompt.py), one quest-log
frame that set MATCH_MIN as a false positive, and one clean bar frame. Every
pin is on a literal or a real frame, never on the constant it guards. Offline.
"""
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

from PIL import Image
import table_prompt as tp

CASES = os.path.join(_ROOT, "test_fixtures", "table_prompt_cases")
BRIGHT_TABLE = os.path.join(CASES, "prompt_on_bright_table_goalleg_t1.jpg")
OVER_DEALER = os.path.join(CASES, "prompt_over_dealer_dealer_circle_f0020.jpg")
LOW_INK = os.path.join(CASES, "prompt_low_ink_recorded_goalleg_t6.jpg")
QUEST_LOG = os.path.join(CASES, "questlog_open_no_prompt_walk2_f0049.jpg")
CLEAN_BAR = os.path.join(_ROOT, "overnight", "failframes", "fail_bar_jukebox_1788562198.jpg")
ANCHOR = os.path.join(_ROOT, "test_fixtures", "table_prompt", "live_arrival.jpg")


def load(p):
    if not os.path.isfile(p):
        raise AssertionError(f"fixture missing: {p}")
    return Image.open(p).convert("RGB")


class OcrPath(unittest.TestCase):

    def test_prompt_over_bright_table_is_seen_by_ocr_not_the_mask(self):
        img = load(BRIGHT_TABLE)
        self.assertLess(tp.score(img), tp.MATCH_MIN, "the mask now sees it; move this case")
        self.assertGreaterEqual(tp.ocr_words(img), 2)
        self.assertTrue(tp.at_table(img))

    def test_prompt_over_the_dealer_is_seen_by_ocr_not_the_mask(self):
        img = load(OVER_DEALER)
        self.assertLess(tp.score(img), tp.MATCH_MIN, "the mask now sees it; move this case")
        self.assertGreaterEqual(tp.ocr_words(img), 2)
        self.assertTrue(tp.at_table(img))

    def test_prompt_with_correlation_but_no_ink_is_seen_by_ocr(self):
        # Goal-leg A/B trial 6 (recorded arm): a clean arrival, dealer ahead,
        # prompt centred. The correlation passed (0.311) and the INK gate
        # rejected it (0.0061 against 0.024).
        img = load(LOW_INK)
        self.assertGreaterEqual(tp.score(img), tp.MATCH_MIN)
        self.assertLess(tp.ink(img), tp.INK_MIN, "the ink gate now passes it; move this case")
        self.assertGreaterEqual(tp.ocr_words(img), 2)
        self.assertTrue(tp.at_table(img))

    def test_quest_log_false_positive_stays_rejected(self):
        img = load(QUEST_LOG)
        self.assertEqual(tp.ocr_words(img), 0)
        self.assertFalse(tp.at_table(img))

    def test_clean_bar_frame_stays_rejected(self):
        img = load(CLEAN_BAR)
        self.assertLess(tp.ocr_words(img), 2)
        self.assertFalse(tp.at_table(img))

    def test_mask_path_still_answers_first(self):
        # A reference-quality arrival: the mask accepts it, so OCR must not be
        # what decides -- and the answer is True either way.
        img = load(ANCHOR)
        self.assertGreaterEqual(tp.score(img), tp.MATCH_MIN)
        self.assertTrue(tp.at_table(img))

    def test_two_words_are_required(self):
        # Pinned as a literal: at one word the corpus was not measured clean.
        self.assertEqual(tp.OCR_MIN_WORDS, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
''')
print("wrote tests/routing/test_at_table_ocr_path.py")
