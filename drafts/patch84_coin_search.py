"""patch84 -- find the coin instead of assuming where it is. Fixes what patch83 broke.

WHAT I BROKE. patch83 moved first_base and third_base up by 0.030 of frame height -- the
correct fix, which the user spotted by eye and which I then measured. The runners reader an
agent had just built anchors its coin template at fixed CROP PIXELS, so every anchor slid
off. An independent skeptic measured it: frames yielding a runner count went 127/150 to
5/150 on HEAD. second_base, which patch83 left alone, was bit-identical -- so it was
unambiguously my change.

The same skeptic found the deeper defect: that box tolerates +-2 PIXELS. At +-3 it loses
187 of 1080 crops, at +-4 it loses ~900. A reader that only works within two pixels of one
exact crop is going to break again on the next geometry change, and this project has two
capture geometries in one session (CLAUDE.md section 3).

SO DELETE THE ANCHOR RATHER THAN MOVE IT. Slide the coin template over the whole crop and
take the best match. There is then nothing to re-measure when a box moves.

MEASURED, 55 recorded frames, both box sets:

    base     anchored (OLD -> HEAD)        searched (OLD -> HEAD)
    third    +0.995 -> -0.048  DEAD        +0.916 -> +0.916
    first    +0.989 -> +0.008  DEAD        +0.918 -> +0.918
    second   +0.982 -> +0.982  (control)   +0.828 -> +0.828

AND IT KEEPS THE DISCRIMINATION, which was the thing to check -- a template slid over a
whole crop can match something everywhere. Against the USER'S OWN 20 confirmed third-base
cards and 120 bare crops:

    CARDS  0.350 .. 0.555          BARE  0.874 .. 0.915
    gap between the card MAX and the bare p05: +0.353

At the existing gate of 0.80: 20 of 20 cards read as cards, 120 of 120 coins as coins. The
searched score on a bare coin is lower than the anchored one (0.92 against 0.99) because
the template no longer sits exactly on its own box -- that is the price, and the gap
absorbs it twenty times over.
"""
import io

P = "local_state.py"
s = io.open(P, encoding="utf-8").read()
NEW = io.open("agent_progress/runners-fix/runners_reader.py", encoding="utf-8").read()

# take the new reader's body, minus its imports and module docstring
import ast
tree = ast.parse(NEW)
keep = [n for n in tree.body
        if not isinstance(n, (ast.Import, ast.ImportFrom))
        and not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                 and isinstance(n.value.value, str))]
lines = NEW.splitlines(True)
start = keep[0].lineno - 1
while start > 0 and lines[start-1].lstrip().startswith("#"):
    start -= 1
body = "".join(lines[start:])

# THE ONE CHANGE: base_coin_score searches instead of anchoring.
OLD_FN = '''    s = img.width / BASE_ANCHOR_W[base]
    x0, y0, x1, y1 = [int(round(v * s)) for v in BASE_COIN_BOX[base]]
    if x0 < 0 or y0 < 0 or x1 > img.width or y1 > img.height:
        return None
    if x1 - x0 < BASE_COIN_N or y1 - y0 < BASE_COIN_N:
        return None
    g = np.asarray(img.convert("L").crop((x0, y0, x1, y1))
                   .resize((BASE_COIN_N, BASE_COIN_N)), dtype=np.float32)
    a = g - g.mean()
    b = t - t.mean()
    d = float(np.sqrt(float((a * a).sum()) * float((b * b).sum())))
    if d <= 0.0:
        return None
    return float((a * b).sum() / d)'''
assert body.count(OLD_FN) == 1, f"coin-score anchor x{body.count(OLD_FN)}"
NEW_FN = '''    # SEARCH, DO NOT ANCHOR. BASE_COIN_BOX is still used -- for the coin's SIZE, which
    # scales with the crop width -- but not for its POSITION, which does not survive a
    # crop-box change. patch83 moved two boxes 0.030 of frame height and the anchored
    # version died: third +0.995 -> -0.048, first +0.989 -> +0.008, while second (the box
    # patch83 left alone) was unchanged. The searched version reads the same under both.
    import cv2
    g = np.asarray(img.convert("L"), dtype=np.float32)
    s = img.width / BASE_ANCHOR_W[base]
    x0, y0, x1, y1 = BASE_COIN_BOX[base]
    side = int(round(max(x1 - x0, y1 - y0) * s))
    if side < 8 or side > min(g.shape):
        return None
    tt = cv2.resize(t.astype(np.float32), (side, side), interpolation=cv2.INTER_LINEAR)
    return float(cv2.matchTemplate(g, tt, cv2.TM_CCOEFF_NORMED).max())'''
body = body.replace(OLD_FN, NEW_FN, 1)

# splice it in, replacing the OLD runners section of local_state
MARK = "# " + "-"*86 + "\n# THE RUNNERS READER (is there a card on this base)\n# " + "-"*86 + "\n"
assert s.count(MARK) == 1, "runners section marker"
head = s[:s.index(MARK)]
out = head + MARK + body + "\n"
ast.parse(out)
io.open(P, "w", encoding="utf-8").write(out)
print("local_state.py: runners reader replaced, coin is SEARCHED not anchored")
