"""at_table() reads the prompt over a BRIGHT background through OCR, and only there.

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
LOW_INK_NO_OCR = os.path.join(CASES, "prompt_low_ink_no_ocr_dealer_circle_f0040.jpg")
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
        # Here the correlation PASSES (0.399) and the INK gate rejects it: the
        # dealer's white body lifts the neighbourhood mean, so few strokes
        # survive the mask. The pin is on the mask PATH as a whole.
        img = load(OVER_DEALER)
        self.assertFalse(tp.ink(img) >= tp.INK_MIN and tp.score(img) >= tp.MATCH_MIN,
                         "the mask path now accepts it; move this case")
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

    def test_prompt_with_correlation_but_no_ink_and_no_ocr_is_accepted(self):
        # demos/dealer_circle f_0040.31: the prompt over the dealer and a bottle.
        # Score 0.414, ink 0.022 (under the old gate by 0.002), OCR reads zero
        # words -- the ONLY path that can accept it is the correlation alone.
        # 21 route frames like it were rejected by the ink gate; every negative
        # on disk scores at most 0.176.
        img = load(LOW_INK_NO_OCR)
        self.assertGreaterEqual(tp.score(img), tp.MATCH_MIN)
        self.assertLess(tp.ink(img), tp.INK_MIN, "ink now passes it; the case has moved")
        self.assertLess(tp.ocr_words(img), 2, "OCR now reads it; the case has moved")
        self.assertTrue(tp.at_table(img))

    def test_wanda_prompt_stays_rejected_without_the_ink_gate(self):
        # The ink gate's stated purpose. Wanda's prompt is a different sentence
        # and the correlation alone rejects it by a wide margin.
        for name in ("wanda_ref.jpg", "wanda_occluded.jpg"):
            img = load(os.path.join(_ROOT, "test_fixtures", "wanda_prompt", name))
            self.assertLess(tp.score(img), 0.15, name)
            self.assertFalse(tp.at_table(img), name)

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
