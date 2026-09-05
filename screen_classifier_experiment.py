"""
Standalone feasibility study: can a purely LOCAL classifier name the game's
screen type well enough to replace the per-poll vision API call, with a safe
abstain and a zero false-positive rate on held-out data?

NOT WIRED INTO ANYTHING. Nothing here is imported by orchestrator.py. It reads
screenshot_log/ and prints numbers. See CLASSIFIER_RESEARCH.md for the writeup.

Run:
    python3 screen_classifier_experiment.py eval    # fit-vs-heldout report
    python3 screen_classifier_experiment.py scan    # classify all logged frames
    python3 screen_classifier_experiment.py time    # per-frame runtime
    python3 screen_classifier_experiment.py sheet <out.png> <file> [...]

Design notes (why these features and not §4b's three brightness scalars):

* The game's art style flickers GLOBALLY every frame. On a screen that is
  visually frozen for 13 seconds the whole-canvas mean oscillates between
  ~52 and ~56 grey levels, frame to frame, forever. Absolute brightness
  features therefore carry a +/- 2 level noise floor that swamps any small
  difference between screen types -- which is the most likely reason §4b's
  "top-left brightness 5.8 +/- 0.7" rule evaporated under cross-validation.
  Every feature here is either gain/offset invariant (normalised cross
  correlation) or computed on a z-normalised canvas.

* The screenshot is the whole 2000x1292 desktop, not the game window: a macOS
  menu bar at the top, a Dock strip on the right, and letterboxing top and
  bottom. Everything is measured inside CANVAS, the game's own rectangle.

* Every feature is a STRUCTURAL anchor -- UI furniture that is present or
  absent by construction -- not a statistic of the scene.
"""

import os
import sys
import time

import cv2
import numpy as np
from PIL import Image

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshot_log")

# ---------------------------------------------------------------- geometry --
# The game canvas inside the 2000x1292 desktop grab. Everything below is in
# canvas pixels (1949 x 1159).
CANVAS = (0, 72, 1949, 1231)

# The scoreboard's static word block: "JACK PEPPER / OPPONENT / ROUND /
# DISCARDS". Present on every in-match screen (turn, transition, result),
# absent on the ban screen and the overworld. Deliberately excludes the digit
# columns on the right, which change.
SB_LABEL = (52, 238, 250, 440)

# Centre of the table. A result modal (WINNER / DEFEAT! / DRAW!) and the
# overworld both fill this with bright artwork; an in-match screen does not.
CENTER = (650, 250, 1300, 850)

# A thin horizontal strip that the phase banners ("PLAY BALL!", "ROUND 3",
# "YOUR TURN", "NEW INNING", "PLAY AS THE BATTER", ...) pass through. Chosen
# to sit BELOW y=613, where the third-base and first-base card slots end, so
# a runner on base cannot be mistaken for banner text.
BANNER = (300, 612, 1650, 642)

# The 5-card hand row at its settled resting position.
HAND = (500, 880, 1450, 1156)

# Frames whose scoreboard crops are averaged into the match template. Five
# consecutive settled-turn frames from the FIT session only.
TEMPLATE_FRAMES = [
    "20260824_200806_371.jpg", "20260824_200809_385.jpg", "20260824_200812_398.jpg",
    "20260824_200815_413.jpg", "20260824_200818_427.jpg",
]

# --------------------------------------------------------------- thresholds -
# Fitted on session S1 ONLY (2026-08-24 20:04-20:26), by a rule declared before
# the held-out sessions were scored: an upper bound is the S1 settled-turn
# maximum times 1.25, a lower bound is the S1 minimum times 0.97 (counts) or
# 0.90 (spread) or 0.75 (top). ncc_sb and cen_frac are cut mid-gap instead --
# their class separation is so wide that any value in the gap is arbitrary.
NCC_SB_MIN = 0.80        # in-match >= 0.981, ban screen <= 0.032, overworld <= 0.202.
                         # Set well above the class gap so that a PARTIAL match --
                         # the anchor drifting outside the +/- SEARCH window and
                         # aliasing onto the box's repeating horizontal rules, which
                         # scores ~0.5 -- is rejected too.
CEN_FRAC_MAX = 0.15      # S1 settled turn <= 0.117, result modal >= 0.224
BANNER_PX_MAX = 68       # S1 settled turn <= 55
HAND_COLS_MIN = 873      # S1 settled turn >= 900
HAND_GAP_MAX = 2         # S1 settled turn <= 1
HAND_TOP_LO, HAND_TOP_HI = 23, 101   # S1 settled turn 31..92
HAND_SPREAD_MIN = 86     # S1 settled turn >= 96.4

BAN_MEAN_MIN = 100.0     # ban / collection notebook pages: canvas mean 112-117
MENU_MEAN_MIN = 60.0     # overworld: 69-81; in-match: 42-59

Z_CARD = 1.6             # z threshold for "this pixel is card-white"
Z_BANNER = 2.2           # z threshold for "this pixel is banner-glyph white"

_TEMPLATE = None


# ------------------------------------------------------------------ helpers -
def load_canvas(path_or_img):
    """Grayscale float array of the game canvas. Accepts a path or a PIL image."""
    img = Image.open(path_or_img) if isinstance(path_or_img, str) else path_or_img
    return np.asarray(img.convert("L").crop(CANVAS), dtype=np.float32)


def _crop(a, box):
    return a[box[1]:box[3], box[0]:box[2]]


def _ncc(a, b):
    """Normalised cross correlation. Invariant to any linear brightness change,
    which is exactly what the frame-to-frame global flicker is."""
    a = a - a.mean()
    b = b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 0 else 0.0


def scoreboard_template(log_dir=LOG_DIR):
    """Average of TEMPLATE_FRAMES' scoreboard word block. In production this
    would ship as a small PNG; here it is rebuilt from the log for
    reproducibility."""
    global _TEMPLATE
    if _TEMPLATE is None:
        acc = None
        for f in TEMPLATE_FRAMES:
            c = _crop(load_canvas(os.path.join(log_dir, f)), SB_LABEL)
            acc = c if acc is None else acc + c
        _TEMPLATE = acc / len(TEMPLATE_FRAMES)
    return _TEMPLATE


# ----------------------------------------------------------------- features -
SEARCH = 32          # +/- pixels searched for the scoreboard anchor


def locate_scoreboard(canvas, tpl):
    """Best normalised match of the scoreboard word block, searched over a
    +/- SEARCH pixel window. Returns (ncc, dx, dy).

    Without this the whole thing is pinned to one window position: measured on a
    settled-turn frame, shifting the grab by 8 px vertically or resizing the game
    window by 1% drops the fixed-position NCC from 0.998 to below the gate.
    That fails safe (everything abstains) but it would silently stop saving any
    API calls the first time the window moved. cv2.matchTemplate costs ~1 ms.
    """
    x0, y0, x1, y1 = SB_LABEL
    win = canvas[max(0, y0 - SEARCH):y1 + SEARCH, max(0, x0 - SEARCH):x1 + SEARCH]
    if win.shape[0] < tpl.shape[0] or win.shape[1] < tpl.shape[1]:
        return _ncc(_crop(canvas, SB_LABEL), tpl), 0, 0
    r = cv2.matchTemplate(win, tpl, cv2.TM_CCOEFF_NORMED)
    _, mx, _, loc = cv2.minMaxLoc(r)
    dx = loc[0] - min(x0, SEARCH)
    dy = loc[1] - min(y0, SEARCH)
    return float(mx), int(dx), int(dy)


def extract_features(canvas, template=None):
    """Seven structural measurements. ~7 ms on a 2000x1292 JPEG."""
    tpl = scoreboard_template() if template is None else template
    mu = float(canvas.mean())
    sd = float(canvas.std()) + 1e-6
    z = (canvas - mu) / sd

    f = {"mean": mu}
    # 1. Is the in-match scoreboard chrome on screen at all, and where?
    f["ncc_sb"], dx, dy = locate_scoreboard(canvas, tpl)
    f["dx"], f["dy"] = dx, dy
    sh = lambda b: (b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy)
    # 2. Is something big and bright covering the centre of the table?
    f["cen_frac"] = float((_crop(z, sh(CENTER)) > Z_CARD).mean())
    # 3. Is a phase banner painted across the middle of the screen?
    f["banner_px"] = int((_crop(z, sh(BANNER)) > Z_BANNER).sum())

    # 4-7. Shape of the card mass in the hand row.
    hm = _crop(z, sh(HAND)) > Z_CARD
    present = hm.any(0)
    idx = np.where(present)[0]
    f["hand_cols"] = int(present.sum())
    f["hand_gap"] = int((~present[idx[0]:idx[-1] + 1]).sum()) if len(idx) else 999
    height = hm.shape[0]
    top = np.where(present, hm.argmax(0), height)
    ok = top < height
    if ok.any():
        f["hand_top"] = float(np.median(top[ok]))
        f["hand_spread"] = float(np.percentile(top[ok], 90) - np.percentile(top[ok], 10))
    else:
        f["hand_top"] = -1.0
        f["hand_spread"] = -1.0
    return f


# --------------------------------------------------------------- classifier -
def classify(canvas, template=None):
    """Returns (verdict, reason, features).

    verdict is one of:
        "turn_settled"       - in-match, five cards dealt and at rest, no banner
        "ban_screen"         - the BANNED CARDS / collection notebook
        "menu_or_overworld"  - the seated table screen, quest list, match start
        "abstain"            - anything else, including every result modal;
                               caller must fall back to the API
    """
    f = extract_features(canvas, template)

    if f["ncc_sb"] < NCC_SB_MIN:
        if f["mean"] >= BAN_MEAN_MIN:
            return "ban_screen", "no scoreboard chrome, notebook-bright canvas", f
        if f["mean"] >= MENU_MEAN_MIN:
            return "menu_or_overworld", "no scoreboard chrome, mid-bright canvas", f
        return "abstain", "no scoreboard chrome and brightness unfamiliar", f

    if f["cen_frac"] > CEN_FRAC_MAX:
        # A result modal (WINNER / DEFEAT! / DRAW!) lands here -- and so does
        # any mid-animation frame with cards flying across the middle of the
        # table. Measured on the labelled set the two are NOT separable by any
        # cheap feature tried (result modals bottom out at cen_frac 0.224,
        # mid-animation tops out at 0.227), so this abstains rather than
        # claiming a screen type it cannot actually tell apart.
        return "abstain", "table centre covered (result modal or mid-animation)", f

    checks = [
        ("banner on screen", f["banner_px"] <= BANNER_PX_MAX),
        ("hand does not span the fan", f["hand_cols"] >= HAND_COLS_MIN),
        ("hole in the hand", f["hand_gap"] <= HAND_GAP_MAX),
        ("hand not at rest height", HAND_TOP_LO <= f["hand_top"] <= HAND_TOP_HI),
        ("hand not fanned", f["hand_spread"] >= HAND_SPREAD_MIN),
    ]
    failed = [name for name, ok in checks if not ok]
    if failed:
        return "abstain", "; ".join(failed), f
    return "turn_settled", "", f


# ------------------------------------------------------- two-frame stillness -
# The single-frame gates above cannot tell a settled hand from one whose middle
# card is still mid-flip: measured false positives 20260824_201924_394 (a HOLE
# in the fan, four cards), 20260824_204124_273, 20260824_221638_341 and
# 20260824_221702_982 (one card squashed mid-flip). All four are structurally
# invisible at the resolution these features work at -- the fan still spans the
# right columns, still sits at the right height, still has no gap wide enough to
# count.
#
# They are trivially visible in TIME. Measured on the log:
#     accepted frames whose hand matches the previous frame : <= 0.443
#     the four false positives                              : 1.02 .. 1.11
# so a second grab settles it with better than a 2x margin. The live loop
# already has this machinery (screen_is_moving / wait_for_screen_to_settle);
# this is the same idea narrowed to the hand row.
HAND = HAND  # (region reused below)
HAND_STILL_MAX = 0.45


def hand_signature(canvas, dx=0, dy=0):
    """z-normalised hand row. Gain/offset invariant, so the global flicker
    cancels."""
    z = (canvas - canvas.mean()) / (canvas.std() + 1e-6)
    return _crop(z, (HAND[0] + dx, HAND[1] + dy, HAND[2] + dx, HAND[3] + dy))


def hand_still(sig_a, sig_b):
    return float(np.abs(sig_a - sig_b).mean())


def classify_pair(canvas_now, canvas_before, template=None):
    """classify() plus the two-frame stillness gate. canvas_before should be a
    grab taken shortly earlier (the log's own spacing is 0.5-2 s; the live loop
    could use ~0.15 s, which is a weaker but cheaper test)."""
    verdict, reason, f = classify(canvas_now, template)
    if verdict != "turn_settled":
        return verdict, reason, f
    d = hand_still(hand_signature(canvas_now), hand_signature(canvas_before))
    f["hand_move"] = d
    if d > HAND_STILL_MAX:
        return "abstain", "hand still moving (%.2f)" % d, f
    return "turn_settled", "", f


# ------------------------------------------------------------ ground truth --
# 646 frames labelled by eye from contact sheets, one every third frame of the
# whole log, BEFORE any classifier existed. Codes:
#   T  settled turn      - in-match, five fully rendered cards at rest, no banner
#   Xs soft negative     - hand complete but a phase banner is up (reading the
#                          hand would succeed; the game is between input windows)
#   Xh hard negative     - in-match, hand absent / partial / face-down card /
#                          mid-flip. Acting here reads a WRONG hand.
#   B  ban screen or collection notebook
#   M  overworld / match-start prompt / menu
#   R  result modal (WINNER / DEFEAT! / DRAW!)
_LABELS_BLOB = (
    "20260824_200458_664:B 20260824_200501_981:B 20260824_200504_992:B 20260824_200521_989:B "
    "20260824_200525_005:B 20260824_200542_484:B 20260824_200545_495:B 20260824_200603_134:B "
    "20260824_200606_149:B 20260824_200639_221:B 20260824_200642_236:B 20260824_200645_248:B "
    "20260824_200648_259:B 20260824_200721_171:B 20260824_200724_181:B 20260824_200727_194:B "
    "20260824_200730_210:B 20260824_200733_221:B 20260824_200736_236:B 20260824_200739_247:B "
    "20260824_200742_261:B 20260824_200745_272:B 20260824_200748_287:B 20260824_200751_303:Xh "
    "20260824_200754_318:Xh 20260824_200757_334:Xh 20260824_200800_342:Xs 20260824_200803_355:Xs "
    "20260824_200806_371:T 20260824_200809_385:T 20260824_200812_398:T 20260824_200815_413:T "
    "20260824_200818_427:T 20260824_200821_434:Xh 20260824_200824_446:Xh 20260824_200827_453:Xh "
    "20260824_200830_460:Xh 20260824_200833_473:T 20260824_200836_488:T 20260824_200839_499:T "
    "20260824_200842_510:T 20260824_200845_524:Xh 20260824_200848_539:Xh 20260824_200851_553:Xh "
    "20260824_200854_568:Xh 20260824_200857_583:T 20260824_200900_599:T 20260824_200903_614:T "
    "20260824_200906_625:T 20260824_200909_638:T 20260824_200912_651:T 20260824_200915_662:T "
    "20260824_200918_673:T 20260824_200921_687:Xh 20260824_200924_698:Xh 20260824_200927_711:Xh "
    "20260824_200930_722:Xh 20260824_200933_737:T 20260824_200936_750:T 20260824_200939_763:T "
    "20260824_200942_777:T 20260824_200945_789:Xh 20260824_200948_797:Xh 20260824_200951_806:Xh "
    "20260824_200954_818:Xh 20260824_200957_834:T 20260824_201000_847:T 20260824_201003_861:T "
    "20260824_201006_870:T 20260824_201009_883:T 20260824_201012_898:T 20260824_201015_914:Xh "
    "20260824_201018_927:Xh 20260824_201021_943:Xh 20260824_201024_958:Xh 20260824_201027_972:Xh "
    "20260824_201030_987:Xh 20260824_201033_999:Xh 20260824_201037_014:T 20260824_201040_030:T "
    "20260824_201043_040:T 20260824_201046_051:T 20260824_201049_059:T 20260824_201052_075:T "
    "20260824_201055_090:T 20260824_201058_102:T 20260824_201101_118:T 20260824_201104_133:T "
    "20260824_201107_149:T 20260824_201110_162:T 20260824_201113_177:T 20260824_201116_190:T "
    "20260824_201119_204:T 20260824_201122_213:T 20260824_201125_223:T 20260824_201128_257:T "
    "20260824_201131_272:Xh 20260824_201134_288:Xh 20260824_201137_302:Xh 20260824_201140_317:Xh "
    "20260824_201143_332:T 20260824_201146_347:T 20260824_201149_363:T 20260824_201152_378:T "
    "20260824_201155_390:T 20260824_201158_405:Xh 20260824_201201_421:Xh 20260824_201204_432:Xh "
    "20260824_201207_447:Xh 20260824_201210_462:T 20260824_201213_481:T 20260824_201216_488:T "
    "20260824_201219_501:T 20260824_201222_513:Xh 20260824_201225_528:Xh 20260824_201228_542:Xh "
    "20260824_201231_557:Xh 20260824_201234_566:T 20260824_201237_576:T 20260824_201240_588:T "
    "20260824_201243_603:T 20260824_201246_612:T 20260824_201249_627:Xh 20260824_201252_641:Xh "
    "20260824_201255_656:Xh 20260824_201258_671:Xh 20260824_201301_689:T 20260824_201304_703:T "
    "20260824_201307_716:T 20260824_201310_736:T 20260824_201313_741:Xh 20260824_201316_754:Xh "
    "20260824_201319_769:R 20260824_201322_783:R 20260824_201325_793:R 20260824_201328_805:R "
    "20260824_201331_820:M 20260824_201334_835:M 20260824_201337_848:M 20260824_201340_860:B "
    "20260824_201343_937:B 20260824_201346_947:B 20260824_201349_962:B 20260824_201352_976:B "
    "20260824_201355_984:B 20260824_201358_997:B 20260824_201402_013:B 20260824_201405_028:B "
    "20260824_201408_044:Xh 20260824_201411_060:Xh 20260824_201414_072:Xh 20260824_201417_083:Xs "
    "20260824_201420_099:T 20260824_201423_112:Xh 20260824_201426_126:T 20260824_201429_142:T "
    "20260824_201432_158:T 20260824_201435_172:T 20260824_201438_187:T 20260824_201441_199:T "
    "20260824_201444_215:Xh 20260824_201447_231:Xh 20260824_201450_243:Xh 20260824_201453_250:Xh "
    "20260824_201456_257:Xh 20260824_201459_272:T 20260824_201502_278:T 20260824_201505_300:T "
    "20260824_201508_313:T 20260824_201511_327:T 20260824_201514_333:T 20260824_201517_348:T "
    "20260824_201520_358:T 20260824_201523_368:T 20260824_201526_372:T 20260824_201529_380:T "
    "20260824_201532_392:T 20260824_201535_402:T 20260824_201538_417:T 20260824_201541_429:Xh "
    "20260824_201544_442:Xh 20260824_201547_456:Xh 20260824_201550_468:T 20260824_201553_481:T "
    "20260824_201556_495:T 20260824_201559_509:T 20260824_201602_521:T 20260824_201605_536:T "
    "20260824_201608_550:Xh 20260824_201611_566:Xh 20260824_201614_578:Xh 20260824_201617_594:Xh "
    "20260824_201620_605:T 20260824_201623_613:T 20260824_201626_620:T 20260824_201629_634:T "
    "20260824_201632_648:T 20260824_201635_662:T 20260824_201638_683:T 20260824_201641_693:T "
    "20260824_201644_705:T 20260824_201647_712:T 20260824_201650_728:T 20260824_201653_743:Xh "
    "20260824_201656_754:Xh 20260824_201659_768:Xh 20260824_201702_783:Xh 20260824_201705_795:T "
    "20260824_201708_809:T 20260824_201711_825:T 20260824_201714_841:T 20260824_201717_854:Xh "
    "20260824_201720_866:Xh 20260824_201723_878:Xh 20260824_201726_889:Xh 20260824_201729_904:Xh "
    "20260824_201732_917:Xh 20260824_201735_932:Xh 20260824_201738_944:Xh 20260824_201741_954:T "
    "20260824_201744_968:T 20260824_201747_980:T 20260824_201750_996:T 20260824_201754_009:T "
    "20260824_201757_024:T 20260824_201800_040:Xh 20260824_201803_052:Xh 20260824_201806_064:Xh "
    "20260824_201809_073:T 20260824_201812_089:T 20260824_201815_103:T 20260824_201818_116:T "
    "20260824_201821_120:T 20260824_201824_135:Xh 20260824_201827_150:Xh 20260824_201830_161:Xh "
    "20260824_201833_176:T 20260824_201836_191:T 20260824_201839_205:T 20260824_201842_219:T "
    "20260824_201845_235:Xh 20260824_201848_250:Xh 20260824_201851_263:Xh 20260824_201854_275:Xh "
    "20260824_201857_291:Xh 20260824_201900_304:T 20260824_201903_312:T 20260824_201906_321:T "
    "20260824_201909_333:T 20260824_201912_346:Xh 20260824_201915_350:Xh 20260824_201918_364:Xh "
    "20260824_201921_379:Xh 20260824_201924_394:Xh 20260824_201927_405:T 20260824_201930_416:T "
    "20260824_201933_427:T 20260824_201936_437:T 20260824_201939_458:T 20260824_201942_467:Xh "
    "20260824_201945_482:Xh 20260824_201948_497:Xh 20260824_201951_509:Xh 20260824_201954_531:Xh "
    "20260824_201957_542:R 20260824_202000_555:R 20260824_202003_571:R 20260824_202006_582:R "
    "20260824_202009_597:R 20260824_202012_608:M 20260824_202015_615:M 20260824_202018_629:B "
    "20260824_202021_641:B 20260824_202024_648:B 20260824_202027_663:B 20260824_202030_676:B "
    "20260824_202033_689:B 20260824_202036_700:B 20260824_202039_714:B 20260824_202042_729:B "
    "20260824_202045_738:Xh 20260824_202048_752:Xh 20260824_202051_767:Xh 20260824_202054_778:Xs "
    "20260824_202057_792:Xs 20260824_202100_806:T 20260824_202103_817:T 20260824_202106_828:T "
    "20260824_202109_844:T 20260824_202112_856:T 20260824_202115_871:T 20260824_202118_886:Xh "
    "20260824_202121_902:Xh 20260824_202124_913:Xh 20260824_202127_922:T 20260824_202130_938:T "
    "20260824_202133_948:T 20260824_202136_960:T 20260824_202139_971:T 20260824_202142_984:Xh "
    "20260824_202145_994:Xh 20260824_202149_005:Xh 20260824_202152_019:T 20260824_202155_032:T "
    "20260824_202158_047:T 20260824_202201_059:T 20260824_202204_071:T 20260824_202207_085:T "
    "20260824_202210_093:T 20260824_202213_105:T 20260824_202216_121:T 20260824_202219_136:T "
    "20260824_202222_146:T 20260824_202225_162:Xh 20260824_202228_172:Xh 20260824_202231_183:Xh "
    "20260824_202234_193:T 20260824_202237_207:T 20260824_202240_219:T 20260824_202243_234:T "
    "20260824_202246_246:T 20260824_202249_254:Xh 20260824_202252_265:Xh 20260824_202255_273:T "
    "20260824_202258_288:T 20260824_202301_298:T 20260824_202304_310:T 20260824_202307_325:T "
    "20260824_202310_330:T 20260824_202313_340:T 20260824_202316_352:Xh 20260824_202319_366:Xh "
    "20260824_202322_379:Xh 20260824_202325_395:Xh 20260824_202357_989:T 20260824_202404_004:T "
    "20260824_202410_019:Xh 20260824_202416_032:Xh 20260824_202422_044:T 20260824_202428_059:T "
    "20260824_202434_070:T 20260824_202440_082:T 20260824_202446_097:Xh 20260824_202452_111:Xh "
    "20260824_202458_126:T 20260824_202504_142:T 20260824_202510_157:Xh 20260824_202516_172:Xh "
    "20260824_202522_188:T 20260824_202528_199:T 20260824_202534_214:T 20260824_202540_228:Xh "
    "20260824_202546_240:Xh 20260824_202552_251:Xh 20260824_202558_266:T 20260824_202604_281:T "
    "20260824_202610_293:Xh 20260824_202616_305:R 20260824_202622_320:M 20260824_203316_822:M "
    "20260824_203318_393:M 20260824_203320_124:M 20260824_203322_015:M 20260824_203323_978:M "
    "20260824_203325_573:B 20260824_203327_319:B 20260824_203329_009:B 20260824_203330_582:B "
    "20260824_203332_155:B 20260824_203333_817:B 20260824_203350_413:B 20260824_203352_019:B "
    "20260824_203353_765:B 20260824_203409_936:B 20260824_203411_601:B 20260824_203413_246:B "
    "20260824_203430_053:B 20260824_203431_634:B 20260824_203433_325:B 20260824_203510_674:B "
    "20260824_203512_385:B 20260824_203514_056:B 20260824_203515_675:B 20260824_203517_238:B "
    "20260824_203519_216:B 20260824_203521_094:B 20260824_203538_118:B 20260824_203539_776:B "
    "20260824_203541_456:B 20260824_203543_104:B 20260824_203559_705:B 20260824_203601_364:B "
    "20260824_203603_033:B 20260824_203619_500:B 20260824_203621_198:B 20260824_203622_936:B "
    "20260824_203639_863:B 20260824_203641_424:B 20260824_203643_163:B 20260824_203715_224:B "
    "20260824_203716_843:B 20260824_203718_513:B 20260824_203720_227:B 20260824_203722_142:B "
    "20260824_203753_638:B 20260824_203755_365:B 20260824_203756_934:B 20260824_203758_624:B "
    "20260824_203800_187:B 20260824_203802_030:B 20260824_203803_634:B 20260824_203805_339:B "
    "20260824_203807_015:B 20260824_203808_720:B 20260824_203810_327:B 20260824_203811_984:B "
    "20260824_203813_616:B 20260824_203815_194:B 20260824_203816_912:B 20260824_203818_634:B "
    "20260824_203820_434:B 20260824_203822_229:B 20260824_203824_121:B 20260824_203825_708:B "
    "20260824_203827_392:B 20260824_203828_993:Xh 20260824_203830_688:Xh 20260824_203832_222:Xh "
    "20260824_203833_783:Xh 20260824_203835_440:Xh 20260824_203836_987:Xh 20260824_203838_670:Xs "
    "20260824_203840_329:T 20260824_203841_867:Xs 20260824_203843_594:T 20260824_203845_153:T "
    "20260824_203847_016:T 20260824_203848_738:T 20260824_203850_350:T 20260824_203851_978:T "
    "20260824_203853_705:T 20260824_203855_415:T 20260824_203857_048:T 20260824_203858_710:Xh "
    "20260824_203900_374:Xh 20260824_203901_951:Xh 20260824_203903_654:Xh 20260824_203905_223:Xh "
    "20260824_203906_946:Xh 20260824_203908_609:Xh 20260824_203910_269:Xh 20260824_203911_844:Xh "
    "20260824_203913_532:T 20260824_203915_100:T 20260824_203916_755:T 20260824_203918_514:T "
    "20260824_203920_366:T 20260824_203922_027:T 20260824_203923_778:T 20260824_203925_441:T "
    "20260824_203927_059:T 20260824_203928_637:T 20260824_203930_332:Xh 20260824_203932_020:Xh "
    "20260824_203933_693:Xh 20260824_203935_243:Xh 20260824_203936_955:Xh 20260824_203938_553:T "
    "20260824_203940_239:T 20260824_203941_849:T 20260824_203943_520:T 20260824_203945_201:T "
    "20260824_203946_795:T 20260824_203948_443:T 20260824_203950_032:T 20260824_203951_792:Xh "
    "20260824_203953_551:Xh 20260824_203955_166:Xh 20260824_203956_808:Xh 20260824_203958_498:Xh "
    "20260824_204000_135:Xh 20260824_204001_899:T 20260824_204003_543:T 20260824_204005_175:T "
    "20260824_204006_777:T 20260824_204008_461:T 20260824_204010_014:Xh 20260824_204011_720:Xh "
    "20260824_204013_261:Xh 20260824_204014_908:Xh 20260824_204016_555:Xh 20260824_204018_121:Xh "
    "20260824_204019_833:T 20260824_204021_495:T 20260824_204023_301:T 20260824_204025_045:T "
    "20260824_204026_601:T 20260824_204028_250:T 20260824_204029_944:T 20260824_204031_731:T "
    "20260824_204033_299:T 20260824_204035_025:T 20260824_204036_628:T 20260824_204038_369:T "
    "20260824_204039_973:Xh 20260824_204041_633:Xh 20260824_204043_231:Xh 20260824_204044_873:Xh "
    "20260824_204046_535:Xh 20260824_204048_145:Xh 20260824_204049_801:Xh 20260824_204051_425:Xh "
    "20260824_204053_228:Xh 20260824_204054_853:Xh 20260824_204056_489:Xh 20260824_204058_034:Xh "
    "20260824_204059_801:T 20260824_204101_485:T 20260824_204103_141:T 20260824_204104_699:T "
    "20260824_204106_408:T 20260824_204108_010:T 20260824_204109_765:T 20260824_204111_502:T "
    "20260824_204113_127:T 20260824_204114_746:Xh 20260824_204116_435:Xh 20260824_204118_004:Xh "
    "20260824_204119_723:Xh 20260824_204121_451:Xh 20260824_204123_188:Xh 20260824_204124_804:T "
    "20260824_221544_745:T 20260824_221546_296:T 20260824_221547_903:T 20260824_221549_427:T "
    "20260824_221550_997:T 20260824_221552_698:T 20260824_221554_279:T 20260824_221555_855:T "
    "20260824_221557_547:T 20260824_221559_102:T 20260824_221600_756:Xh 20260824_221602_352:Xh "
    "20260824_221603_850:Xh 20260824_221605_520:Xh 20260824_221607_137:Xh 20260824_221608_696:Xh "
    "20260824_221610_354:Xh 20260824_221611_877:T 20260824_221613_550:T 20260824_221615_166:T "
    "20260824_221616_707:T 20260824_221618_336:T 20260824_221619_963:T 20260824_221621_783:T "
    "20260824_221623_459:T 20260824_221625_153:T 20260824_221626_748:T 20260824_221628_295:Xh "
    "20260824_221630_034:Xh 20260824_221631_688:Xh 20260824_221633_427:Xh 20260824_221635_117:Xh "
    "20260824_221636_781:Xh 20260824_221638_341:Xh 20260824_221639_990:T 20260824_221641_650:T "
    "20260824_221643_200:T 20260824_221644_836:T 20260824_221646_384:T 20260824_221647_926:T "
    "20260824_221649_652:T 20260824_221651_219:T 20260824_221652_954:Xh 20260824_221654_486:Xh "
    "20260824_221656_067:Xh 20260824_221657_709:Xh 20260824_221659_237:Xh 20260824_221700_843:Xh "
    "20260824_221702_470:Xh 20260824_221704_026:T 20260824_221705_850:T 20260824_221707_447:T "
    "20260824_221709_228:T 20260824_221710_960:T 20260824_221712_702:T 20260824_221714_735:T "
    "20260824_221716_430:T 20260824_221718_076:T 20260824_221719_762:Xh 20260824_221721_403:Xh "
    "20260824_221723_155:Xh 20260824_221725_389:Xh 20260824_221727_015:Xh 20260824_221728_603:R "
    "20260824_221730_210:R 20260824_221731_846:R 20260824_221733_313:R 20260824_221734_789:R "
    "20260824_221736_294:R 20260824_221737_858:M 20260824_221739_664:M 20260824_221741_243:M "
    "20260825_165852_793:M 20260825_165854_537:M 20260825_165856_225:M 20260825_165857_833:M "
    "20260825_165859_442:B 20260825_165901_149:B 20260825_165902_695:B 20260825_165904_394:B "
    "20260825_165905_955:B 20260825_165922_690:B 20260825_165924_368:B 20260825_165941_158:B "
    "20260825_165942_829:B 20260825_165959_824:B 20260825_170001_500:B 20260825_170018_388:B "
    "20260825_170035_203:B 20260825_170036_823:B 20260825_170038_487:B 20260825_170040_238:B "
    "20260825_170041_971:B 20260825_170043_525:B 20260825_170115_678:B 20260825_170117_357:B "
    "20260825_170118_935:B 20260825_170120_554:B 20260825_170122_254:B 20260825_170123_885:B "
    "20260825_170125_433:B 20260825_170127_121:B 20260825_170128_765:B 20260825_170130_484:B "
    "20260825_170132_165:B 20260825_170133_868:B 20260825_170135_502:B 20260825_170137_155:B "
    "20260825_170138_743:B 20260825_170140_418:B 20260825_170142_104:Xh 20260825_170143_789:Xh "
    "20260825_170145_513:Xh 20260825_170147_152:Xh "
)


def labels():
    out = {}
    for tok in _LABELS_BLOB.split():
        name, code = tok.rsplit(":", 1)
        out[name + ".jpg"] = code
    return out


def session_of(fname):
    """Sessions are contiguous runs of play separated by hours. Held-out splits
    MUST be by session: consecutive frames are near-duplicates and a random
    split leaks."""
    day, hhmmss, _ = fname[:-4].split("_")
    if day == "20260825":
        return "S4"
    hh, mm = int(hhmmss[:2]), int(hhmmss[2:4])
    if hh == 22:
        return "S3"
    return "S1" if (hh == 20 and mm < 30) else "S2"


FIT_SESSIONS = ("S1",)
HELDOUT_SESSIONS = ("S2", "S3", "S4")


# ------------------------------------------------------------- evaluation ---
POSITIVE = "turn_settled"
CLASS_OF = {"T": "turn_settled", "B": "ban_screen", "M": "menu_or_overworld",
            "R": "abstain", "Xs": "abstain", "Xh": "abstain"}


def evaluate(log_dir=LOG_DIR):
    gt = labels()
    tpl = scoreboard_template(log_dir)
    rows = []
    for fname, code in sorted(gt.items()):
        v, why, f = classify(load_canvas(os.path.join(log_dir, fname)), tpl)
        rows.append((fname, session_of(fname), code, v, why, f))

    for title, sessions in (("FIT  (S1)", FIT_SESSIONS),
                            ("HELD OUT (S2+S3+S4)", HELDOUT_SESSIONS)):
        sub = [r for r in rows if r[1] in sessions]
        print("\n=== %s   n=%d frames, sessions=%s" % (title, len(sub), ",".join(sessions)))
        codes = sorted({r[2] for r in sub})
        print("    %-4s %5s | %s" % ("true", "n", "  ".join("%-17s" % c for c in
              ["turn_settled", "ban_screen", "menu_or_overworld", "abstain"])))
        for c in codes:
            g = [r for r in sub if r[2] == c]
            counts = {k: sum(1 for r in g if r[3] == k) for k in
                      ["turn_settled", "ban_screen", "menu_or_overworld", "abstain"]}
            print("    %-4s %5d | %s" % (c, len(g), "  ".join(
                "%-17d" % counts[k] for k in
                ["turn_settled", "ban_screen", "menu_or_overworld", "abstain"])))

        pos = [r for r in sub if r[3] == POSITIVE]
        fp = [r for r in pos if r[2] != "T"]
        neg_n = sum(1 for r in sub if r[2] != "T")
        tp = len(pos) - len(fp)
        tot_t = sum(1 for r in sub if r[2] == "T")
        print("    settled-turn coverage : %d/%d = %.1f%% of true settled turns"
              % (tp, tot_t, 100.0 * tp / tot_t if tot_t else 0))
        print("    FALSE POSITIVES       : %d  (out of %d non-settled frames = %.2f%%)"
              % (len(fp), neg_n, 100.0 * len(fp) / neg_n if neg_n else 0))
        for r in fp:
            print("        FP %s  true=%s  %s" % (r[0], r[2],
                  " ".join("%s=%s" % (k, round(r[5][k], 3)) for k in
                           ("banner_px", "hand_cols", "hand_gap", "hand_top"))))
        for kind in ("Xh", "Xs"):
            g = [r for r in sub if r[2] == kind]
            bad = [r for r in g if r[3] == POSITIVE]
            print("    %s negatives          : %d, of which %d slipped through" % (kind, len(g), len(bad)))
    return rows


# Frames confirmed BY EYE, at full resolution, to be false positives of the
# single-frame rule. Found by auditing every predicted positive in the held-out
# sessions (278 frames) plus every stillness-flagged positive in the fit
# session. See CLASSIFIER_RESEARCH.md.
KNOWN_FALSE_POSITIVES = {
    "20260824_201924_394.jpg": "S1 hole in the fan - only four cards, table visible through the gap",
    "20260824_201417_083.jpg": "S1 OPPONENT'S TURN banner still fading (hand itself is correct)",
    "20260824_204124_273.jpg": "S2 middle card squashed mid-flip",
    "20260824_221638_341.jpg": "S3 fourth card squashed mid-flip",
    "20260824_221702_982.jpg": "S3 middle card squashed mid-flip",
}


def pairs(log_dir=LOG_DIR, max_gap_s=5.0):
    """Re-run the whole log with the two-frame stillness gate, using each
    frame's predecessor in the log as the second grab."""
    import datetime
    tpl = scoreboard_template(log_dir)
    files = sorted(f for f in os.listdir(log_dir) if f.endswith(".jpg"))

    def stamp(f):
        d, hms, ms = f[:-4].split("_")
        return (datetime.datetime.strptime(d + hms, "%Y%m%d%H%M%S")
                + datetime.timedelta(milliseconds=int(ms)))

    prev_sig = prev_t = None
    one, two, dropped = {}, {}, []
    for f in files:
        c = load_canvas(os.path.join(log_dir, f))
        v1, _, _ = classify(c, tpl)
        one[f] = v1
        sig, t = hand_signature(c), stamp(f)
        v2 = v1
        if v1 == "turn_settled":
            if prev_sig is None or (t - prev_t).total_seconds() > max_gap_s:
                v2 = "abstain"
            else:
                d = hand_still(sig, prev_sig)
                if d > HAND_STILL_MAX:
                    v2 = "abstain"
                    dropped.append((f, d))
        two[f] = v2
        prev_sig, prev_t = sig, t

    for name, tbl in (("single frame", one), ("two frame  ", two)):
        n = sum(1 for v in tbl.values() if v == "turn_settled")
        print("%s : %4d turn_settled of %d frames (%.1f%%)"
              % (name, n, len(files), 100.0 * n / len(files)))
    print("dropped by the stillness gate: %d" % len(dropped))
    still_pos = [f for f in KNOWN_FALSE_POSITIVES if two.get(f) == "turn_settled"]
    print("known false positives still accepted: %d  %s"
          % (len(still_pos), ", ".join(sorted(still_pos)) or "-"))
    for f, d in sorted(dropped, key=lambda t: -t[1])[:6]:
        print("   dropped %s  hand_move=%.2f  %s" % (f[:-4], d, "<-- FP" if f in KNOWN_FALSE_POSITIVES else ""))
    return one, two


def scan(log_dir=LOG_DIR):
    """Classify every logged frame, not just the labelled sample."""
    tpl = scoreboard_template(log_dir)
    files = sorted(f for f in os.listdir(log_dir) if f.endswith(".jpg"))
    counts, per_sess = {}, {}
    out = []
    t0 = time.time()
    for f in files:
        v, why, _ = classify(load_canvas(os.path.join(log_dir, f)), tpl)
        counts[v] = counts.get(v, 0) + 1
        per_sess.setdefault(session_of(f), {}).setdefault(v, 0)
        per_sess[session_of(f)][v] += 1
        out.append((f, v))
    print("scanned %d frames in %.1fs (%.1f ms/frame)"
          % (len(files), time.time() - t0, 1000 * (time.time() - t0) / len(files)))
    for k, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print("  %-18s %5d  %5.1f%%" % (k, n, 100.0 * n / len(files)))
    for s in sorted(per_sess):
        print("  %s: %s" % (s, per_sess[s]))
    return out


def timeit(log_dir=LOG_DIR, n=200):
    tpl = scoreboard_template(log_dir)
    files = sorted(f for f in os.listdir(log_dir) if f.endswith(".jpg"))[:n]
    paths = [os.path.join(log_dir, f) for f in files]
    t0 = time.time()
    imgs = [load_canvas(p) for p in paths]
    t1 = time.time()
    for a in imgs:
        classify(a, tpl)
    t2 = time.time()
    print("decode+crop : %.2f ms/frame" % (1000 * (t1 - t0) / len(paths)))
    print("classify    : %.2f ms/frame" % (1000 * (t2 - t1) / len(paths)))
    print("total       : %.2f ms/frame" % (1000 * (t2 - t0) / len(paths)))


def sheet(out_png, files, cols=3, width=500, log_dir=LOG_DIR):
    """Contact sheet used to build the ground truth: full canvas over a zoom of
    the hand row and prompt strip. Kept so the labelling can be re-checked."""
    from PIL import ImageDraw
    cells = []
    for f in files:
        im = Image.open(os.path.join(log_dir, f)).convert("L").crop(CANVAS)
        cw, ch = im.size
        band = im.crop((int(cw * .20), int(ch * .70), int(cw * .99), int(ch * .99)))
        parts = [im.resize((width, int(width * ch / cw)), Image.LANCZOS),
                 band.resize((width, int(width * band.height / band.width)), Image.LANCZOS)]
        c = Image.new("L", (width, sum(p.height for p in parts) + 2), 0)
        y = 0
        for p in parts:
            c.paste(p, (0, y)); y += p.height + 2
        cells.append(c)
    h = max(c.height for c in cells) + 15
    sh = Image.new("L", (cols * width, ((len(cells) + cols - 1) // cols) * h), 0)
    d = ImageDraw.Draw(sh)
    for i, c in enumerate(cells):
        x, y = (i % cols) * width, (i // cols) * h
        sh.paste(c, (x, y + 15))
        d.text((x + 3, y + 2), "[%d] %s" % (i, files[i][:-4]), fill=255)
    sh.save(out_png)
    return out_png


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "eval"
    if cmd == "eval":
        evaluate()
    elif cmd == "scan":
        scan()
    elif cmd == "pairs":
        pairs()
    elif cmd == "time":
        timeit()
    elif cmd == "sheet":
        print(sheet(sys.argv[2], sys.argv[3:]))
    else:
        print(__doc__)
