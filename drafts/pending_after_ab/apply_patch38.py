"""patch38: at_table() retries the stroke mask on a brightness-normalised copy
of a DARK frame.

ab4 trial 10 (2026-09-08 00:2x): the character stood at the dealer's table
with "Baseball Cards [] Play ($50)" on screen for three iterations
(it61-63; frame mean 75/255) and at_table() said False on every one; a gain
of 1.2 made the same frames True. Measured before this landed: tonight's 21
arrival frames 18 raw -> 21 raw-or-normalised; 500 frames at k < 185 (never
at the prompt) 0 false positives raw and 0 normalised-only. The stroke mask
keeps a pixel above STROKE_BRIGHT (175): dim white text in a dark capture
never reaches it. Usage: python apply_patch38.py [ROOT].
"""
import os, sys
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
P = os.path.join(ROOT, "table_prompt.py"); T = os.path.join(ROOT, "tests", "routing", "test_at_table_ocr_path.py")
p = open(P).read(); t = open(T).read()
if "DARK_MEAN" in p:
    raise SystemExit("ALREADY APPLIED")
edits_p = [
 ('''MIN_CONTRAST = 6.0        # std-dev of the raw patch; below this there is no text
''', '''MIN_CONTRAST = 6.0        # std-dev of the raw patch; below this there is no text
# A DARK capture is retried with its brightness normalised: the mask keeps a
# pixel above STROKE_BRIGHT, and dim white text in a frame whose mean is ~75
# never reaches it (ab4 trial 10 stood at the prompt for three iterations
# reading False; gain 1.2 read True). Gain = min(DARK_GAIN_CAP, DARK_MEAN /
# mean), applied only when the mean is under DARK_MEAN. Measured: 21/21
# arrival frames against 18/21 raw, 0 new false positives on 500 route frames.
DARK_MEAN = 90.0
DARK_GAIN_CAP = 1.5
'''),
 ('''    if score(img) >= MATCH_MIN:
        return True
    return ocr_says_prompt(img)
''', '''    if score(img) >= MATCH_MIN:
        return True
    if ocr_says_prompt(img):
        return True
    normalised = _normalised_if_dark(img)
    return normalised is not None and score(normalised) >= MATCH_MIN


def _normalised_if_dark(img):
    """The frame with its brightness scaled toward DARK_MEAN, or None when it
    is not dark (mean >= DARK_MEAN) -- the raw verdict then stands."""
    arr = np.asarray(img.convert("RGB") if hasattr(img, "convert") else img)
    mean = float(arr.mean())
    if mean >= DARK_MEAN or mean <= 0:
        return None
    gain = min(DARK_GAIN_CAP, DARK_MEAN / mean)
    return Image.fromarray(np.clip(arr.astype(np.float32) * gain, 0, 255).astype(np.uint8))
'''),
]
edits_t = [
 ('''    def test_wanda_prompt_stays_rejected_without_the_ink_gate(self):
''', '''    def test_a_dark_prompt_frame_is_seen_after_brightness_normalisation(self):
        # ab4 trial 10, it062: the prompt on screen in a capture whose mean is
        # 75/255; the raw mask scores under MATCH_MIN, the normalised copy
        # scores above it. Pinned: the raw path alone must NOT accept it (so
        # the test cannot pass on the mask), and the verdict is True.
        im = Image.open(os.path.join(CASES, "prompt_dark_ab4_t10_it062.jpg")).convert("RGB")
        self.assertLess(tp.score(im), tp.MATCH_MIN, "the raw mask would already see it: fixture is wrong")
        self.assertEqual((tp.DARK_MEAN, tp.DARK_GAIN_CAP), (90.0, 1.5))
        self.assertTrue(tp.at_table(im))
        norm = tp._normalised_if_dark(im)
        self.assertIsNotNone(norm)
        self.assertGreaterEqual(tp.score(norm), tp.MATCH_MIN)

    def test_a_bright_frame_is_not_normalised(self):
        im = Image.open(os.path.join(CASES, "questlog_open_no_prompt_walk2_f0049.jpg")).convert("RGB")
        self.assertIsNone(tp._normalised_if_dark(Image.fromarray(np.full((120, 160, 3), 120, np.uint8))))
        self.assertFalse(tp.at_table(im))

    def test_wanda_prompt_stays_rejected_without_the_ink_gate(self):
'''),
]
for a, b in edits_p: assert p.count(a) == 1, ("table_prompt anchor", p.count(a))
for a, b in edits_t: assert t.count(a) == 1, ("test anchor", t.count(a))
for a, b in edits_p: p = p.replace(a, b)
for a, b in edits_t: t = t.replace(a, b)
if "import numpy as np" not in t:
    t = t.replace("from PIL import Image\n", "from PIL import Image\nimport numpy as np\n", 1)
open(P, "w").write(p); open(T, "w").write(t); print("patch38 applied to", ROOT)
