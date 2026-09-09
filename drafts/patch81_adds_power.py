"""patch81 -- ask the tactics card the question the DECISION asks: does it add power?

WHY THE 4-WAY NAME WAS THE WRONG QUESTION. CLAUDE.md section 4: only SWING_BOOST and
PITCH_BOOST add power; speed and fielding boosts carry a nonzero bonus that adds NONE.
decision_engine only ever branches on that. Naming which of the four a card is was always
more than the caller needs, and a 4-way answer is a harder problem than a 2-way one.

AND MY 4-WAY NUMBER WAS OPTIMISTIC. I reported 78% coverage at 100% accuracy from a
leave-one-hand-out that grouped by "the vision card list changed" -- but two hands from the
same match holding the same cards in a different order land in different groups while being
nearly the same picture, so the estimate leaked (CLAUDE.md 10.22, which I wrote this
morning). Trained on one session and tested on another, hours apart, the same reader gives
30% coverage at 0.88.

MEASURED ACROSS SESSIONS (train runs 1-2, test run 5, 198 train / 61 test):

    gate     4-WAY name                        BINARY adds-power
    0.70     41 right 10 WRONG  84% read       42 right  9 WRONG  84% read
    0.77     37 right  1 WRONG  62% read       38 right  0 WRONG  62% read
    0.85     22 right  0 WRONG  36% read       22 right  0 WRONG  36% read

0.77 on the binary question is the operating point: ZERO wrong on unseen data at 62%
coverage, where the 4-way name still gets one wrong there. An abstention costs one paid
call; a wrong answer plays a speed boost as if it added power in a $50 match.

WHAT IS STILL OPEN, and it is the honest gap: 38% of tactics cards abstain, so a hand
holding one is fully local about three times in five. Closing that needs training data from
MORE SESSIONS -- the loss is cross-session generalisation, not the method.
"""
import io

P = "local_hand.py"
s = io.open(P, encoding="utf-8").read()

ANCHOR = "def read_tactics_type(img, slot):"
assert s.count(ANCHOR) == 1, f"anchor x{s.count(ANCHOR)}"

NEW = '''# THE TWO TYPES THAT ADD POWER. CLAUDE.md section 4: a speed or fielding boost carries a
# nonzero bonus that adds NONE, and decision_engine branches on exactly this.
ADDS_POWER = frozenset({"swing_boost", "pitch_boost"})
# The binary question is easier than the 4-way name and it is the one the caller asks.
# Measured across SESSIONS (train on one, test on another hours later, 198/61 cards):
#     gate 0.70   binary 42 right  9 WRONG   84% read      4-way 41 right 10 WRONG
#     gate 0.77   binary 38 right  0 WRONG   62% read      4-way 37 right  1 WRONG
#     gate 0.85   binary 22 right  0 WRONG   36% read
# 0.77 is the operating point: zero wrong on unseen data at the best coverage that holds.
MIN_ADDS_POWER_SCORE = 0.77


def reads_adds_power(img, slot):
    """(True|False, score) for "does this tactics card add power", or (None, score).

    None means NOT READ and the caller must ask the paid model. It never guesses: a speed
    boost played as if it added power is a wrong card in a $50 match, and an abstention is
    one API call.
    """
    bank = _type_templates()
    v = tactics_banner_vector(img, slot)
    if bank is None or v is None:
        return None, 0.0
    vecs, types = bank
    scores = vecs @ v
    k = int(scores.argmax())
    best = float(scores[k])
    if best < MIN_ADDS_POWER_SCORE:
        return None, best
    return (types[k] in ADDS_POWER), best


'''
s = s.replace(ANCHOR, NEW + ANCHOR, 1)

# read_hand carries it alongside the name
OLD_ROW = '''        if kind == "tactics":
            # The type is what decides play, so it is read here and NEVER guessed.
            row["type"], ts = read_tactics_type(img, i)
            row["type_score"] = round(ts, 3)'''
assert s.count(OLD_ROW) == 1, "row anchor"
NEW_ROW = '''        if kind == "tactics":
            # The type is what decides play, so it is read here and NEVER guessed.
            row["type"], ts = read_tactics_type(img, i)
            row["type_score"] = round(ts, 3)
            # AND THE QUESTION THE DECISION ACTUALLY ASKS, which is easier and therefore
            # answered more often: does this card add power at all?
            row["adds_power"], aps = reads_adds_power(img, i)
            row["adds_power_score"] = round(aps, 3)'''
s = s.replace(OLD_ROW, NEW_ROW, 1)
assert "reads_adds_power" in s and s.count("MIN_ADDS_POWER_SCORE") >= 2
io.open(P, "w", encoding="utf-8").write(s)
print("local_hand.py: reads_adds_power added and carried on every tactics row")
