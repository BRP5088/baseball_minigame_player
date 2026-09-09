"""patch74 -- read a TACTICS CARD'S TYPE from its banner. It is the field that decides play."""
import io

P = "local_hand.py"
s = io.open(P, encoding="utf-8").read()

ANCHOR = "def read_hand(img):"
assert s.count(ANCHOR) == 1, f"read_hand anchor x{s.count(ANCHOR)}"

GAP_OLD = """  * A TACTICS CARD'S TYPE IS NOT READ, and that is the gap that matters. CLAUDE.md section
    4: only swing and pitch boosts add power, while speed and fielding boosts carry a
    nonzero bonus that adds NONE. orchestrator derives that type from the card's NAME, and
    no banner is read here -- so a hand holding a tactics card still needs the paid call to
    decide what to play. 14 of 15 measured hands hold at least one."""
assert s.count(GAP_OLD) == 1, "KNOWN GAPS tactics bullet"
GAP_NEW = """  * A TACTICS CARD'S TYPE IS READ FROM ITS BANNER, and it ABSTAINS rather than guess.
    CLAUDE.md section 4: only swing and pitch boosts add power, while speed and fielding
    boosts carry a nonzero bonus that adds NONE, so a speed boost read as a swing boost
    plays the wrong card for $50. Measured leave-one-HAND-out over 83 cards in 30 hands:
    the right answers score 0.773 and above, every one of the 10 errors scores 0.761 or
    below, and MIN_TYPE_SCORE sits in that gap. A card below it returns type None.
  * A TACTICS CARD'S BONUS is read only when its digit happens to be isolated enough for
    the digit finder: measured 23 of 83, with ZERO wrong. The other 60 come back None."""

TYPE_CODE = '''# ---------------------------------------------------------------------------------------
# THE TACTICS TYPE, FROM THE BANNER. This is the field that decides play -- CLAUDE.md
# section 4 records that only SWING_BOOST and PITCH_BOOST add power, while speed and
# fielding boosts carry a nonzero bonus that adds NONE -- so it is guarded harder than any
# digit here. The disc cannot answer it; the BANNER can, because each card writes its name
# across the middle in white on a dark band and that is a fixed game asset like the digits.
#
# MEASURED, leave-one-HAND-out over 83 located tactics cards in 30 distinct hands (a hand
# sampled twice is nearly the same picture; scoring across the pair measures JPEG, not
# recognition):
#
#     top score   RIGHT p05 0.773    WRONG MAX 0.761      no overlap
#     raw accuracy 73/83; all 10 errors fall below the worst right answer
#
# The MARGIN over the runner-up type does NOT separate (right p05 0.112 against wrong max
# 0.203) and is not used -- measured and dropped, per CLAUDE.md 10.4.
TACTICS_TEMPLATES = os.path.join(_HERE, "tactics_templates.npz")
MIN_TYPE_SCORE = 0.77
# The banner's box relative to the slot's TACTICS anchor, in the 979-wide crop the anchors
# were measured in, and scaled with them.
BANNER_BOX = (-50, 18, 130, 70)
BANNER_SIZE = (64, 20)

_type_cache = None


def _type_templates():
    global _type_cache
    if _type_cache is None:
        if not os.path.exists(TACTICS_TEMPLATES):
            return None
        z = np.load(TACTICS_TEMPLATES)
        _type_cache = (z["vectors"], [str(t) for t in z["types"]])
    return _type_cache


def tactics_banner_vector(img, slot):
    """The normalised banner patch for a slot, or None when it falls off the crop."""
    if not (0 <= slot < len(SLOT_TACTICS)):
        return None
    sc = img.width / ANCHOR_W
    ax, ay = SLOT_TACTICS[slot][0] * sc, SLOT_TACTICS[slot][1] * sc
    x0, y0, x1, y1 = BANNER_BOX
    box = (max(0, int(ax + x0 * sc)), max(0, int(ay + y0 * sc)),
           min(img.width, int(ax + x1 * sc)), min(img.height, int(ay + y1 * sc)))
    if box[2] - box[0] < 10 or box[3] - box[1] < 6:
        return None
    a = np.asarray(img.crop(box).convert("L").resize(BANNER_SIZE, Image.LANCZOS),
                   dtype=np.float32).ravel()
    a = a - a.mean()
    n = np.linalg.norm(a)
    return None if n < 1e-6 else a / n


def read_tactics_type(img, slot):
    """(type, score) for the tactics card in `slot`, or (None, score) when unsure.

    None means NOT READ and the caller must ask the paid model. It never guesses: the
    whole value of this reader is that its answer can be trusted without a second opinion.
    """
    bank = _type_templates()
    v = tactics_banner_vector(img, slot)
    if bank is None or v is None:
        return None, 0.0
    vecs, types = bank
    scores = vecs @ v
    k = int(scores.argmax())
    best = float(scores[k])
    return (types[k] if best >= MIN_TYPE_SCORE else None), best


'''

s2 = s.replace(GAP_OLD, GAP_NEW, 1).replace(ANCHOR, TYPE_CODE + ANCHOR, 1)

# read_hand must now report the type on a tactics row.
OLD_ROW = '''    for t in find_tactics(img):
        if all(abs(t["x"] - o["x"]) > 20 for o in out):
            out.append({"x": t["x"], "kind": "tactics", "digit": None, "score": 0.0})'''
assert s2.count(OLD_ROW) == 1, "ungated tactics row anchor"
NEW_ROW = '''    for t in find_tactics(img):
        if all(abs(t["x"] - o["x"]) > 20 for o in out):
            out.append({"x": t["x"], "kind": "tactics", "digit": None, "score": 0.0,
                        "type": None})'''

OLD_FAN = '''        _, x, kind, circle = best[i]
        digit, sc = read_digit(img, circle) if circle else (None, 0.0)
        out.append({"x": x, "kind": kind, "digit": digit, "score": round(sc, 3)})'''
assert s2.count(OLD_FAN) == 1, "fan row anchor"
NEW_FAN = '''        _, x, kind, circle = best[i]
        digit, sc = read_digit(img, circle) if circle else (None, 0.0)
        row = {"x": x, "kind": kind, "digit": digit, "score": round(sc, 3)}
        if kind == "tactics":
            # The type is what decides play, so it is read here and NEVER guessed.
            row["type"], ts = read_tactics_type(img, i)
            row["type_score"] = round(ts, 3)
        out.append(row)'''

OLD_EMPTY = '''            out.append({"x": int(SLOT_PLAYER[i][0] * s), "kind": "tactics", "digit": None,
                        "score": 0.0})'''
assert s2.count(OLD_EMPTY) == 1, "empty-slot anchor"
NEW_EMPTY = '''            t, ts = read_tactics_type(img, i)
            out.append({"x": int(SLOT_PLAYER[i][0] * s), "kind": "tactics", "digit": None,
                        "score": 0.0, "type": t, "type_score": round(ts, 3)})'''

s2 = s2.replace(OLD_ROW, NEW_ROW, 1).replace(OLD_FAN, NEW_FAN, 1).replace(OLD_EMPTY, NEW_EMPTY, 1)
assert "def read_tactics_type" in s2 and "MIN_TYPE_SCORE" in s2
io.open(P, "w", encoding="utf-8").write(s2)
print("local_hand.py: tactics type reader added and wired into read_hand")
