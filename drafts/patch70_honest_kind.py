"""patch70 -- the local reader stops claiming a card is a PLAYER card.

It never had evidence for that claim. read_hand labelled every circle the digit finder
located "player", and on 2026-09-09 that read a tactics card's bonus as a batter's power:
"Power Swing bonus 2" came back as a power-2 batter at score 0.972. Playing a boost as a
batter is a wrong card in a $50 match, and only the vision audit caught it.

Three candidate discriminators were measured against both populations, labels from the
paid model (9 tactics discs, 74 player discs):

    ring darkness around the disc      tactics p05 0.32 p50 0.54   player p05 0.09 p95 0.40   OVERLAP
    biggest dark blob beside the disc  tactics min 30 p50 82       player p05 58 p95 76       OVERLAP
    shield present                     23% of PLAYER cards show no shield at all             USELESS

No threshold sits between these populations, so none is invented (CLAUDE.md 10.4). What
replaces the claim is the truth: a digit was read here, and the card type is NOT known.

    "tactics"  the fused wreath detector fired -- that IS evidence
    "unknown"  a digit was found; the card type is not established

Nothing reports "player" any more, so no caller can act on a kind this reader cannot see.

THE MEASURED CANDIDATE, for when the corpus is bigger. The code itself says where the
answer lives: orchestrator derives PHASE from the hand card's banner name and a tactics
card's TYPE from its name, so one banner reader would close three of the four gaps that
keep the paid call on the turn. Measured today at 11 of 34 discs with strict matching and
221 ms a hand -- the banners of overlapped cards read as "ATTER", "ITCHER", "CHER" or not
at all. Too little recall to gate a decision, and 4 tactics examples is too few to measure
the false-attribution risk from a neighbouring card's banner. Every played turn adds one
labelled example.
"""
import io

P = "local_hand.py"
src = io.open(P, encoding="utf-8").read()

OLD_CALL = '''        d, s = read_digit(img, c)
        out.append({"x": c[0], "kind": "player", "digit": d, "score": round(s, 3)})'''
NEW_CALL = '''        d, s = read_digit(img, c)
        # NOT "player". See the module docstring: no measured quantity separates a
        # player disc from a tactics disc, and calling one the other plays a boost as
        # a batter for $50.
        out.append({"x": c[0], "kind": "unknown", "digit": d, "score": round(s, 3)})'''
assert src.count(OLD_CALL) == 1, f"call anchor x{src.count(OLD_CALL)}"

OLD_DOC = '''    Each entry is {"x", "kind", "digit", "score"}. `kind` is "player" or "tactics".'''
NEW_DOC = '''    Each entry is {"x", "kind", "digit", "score"}. `kind` is "tactics" when the fused
    wreath detector fired, and otherwise "unknown" -- NEVER "player".

    THAT IS DELIBERATE AND IT COST A WRONG CARD TO LEARN. This used to say "player" for
    every circle the digit finder located, and on 2026-09-09 it read a tactics card's
    "Power Swing bonus 2" as a power-2 batter at score 0.972. A score gate cannot catch
    that -- the digit was read correctly; the CARD was misidentified. Three discriminators
    were measured against both populations and all three overlap (ring darkness, the
    biggest dark blob beside the disc, and shield presence -- 23% of player cards show no
    shield). So the kind is reported as unknown until something measured can establish it.'''
assert src.count(OLD_DOC) == 1, f"doc anchor x{src.count(OLD_DOC)}"

OLD_GAP = '''  * a tactic and a player card are told apart by the BANNER, not the circle, and no
    banner is read here.'''
NEW_GAP = '''  * a tactic and a player card are told apart by the BANNER, not the circle, and no
    banner is read here -- so this reader NEVER reports "player", only "tactics" (the
    fused wreath) or "unknown". orchestrator derives the batting/pitching PHASE from that
    same banner and a tactics card's TYPE from its name, so one banner reader would close
    three of the four fields that keep the paid vision call on every turn. Measured
    2026-09-09: 11 of 34 discs named correctly at 221 ms a hand, because an overlapped
    card's banner reads "ATTER", "ITCHER" or nothing. Not enough recall yet.'''
assert src.count(OLD_GAP) == 1, f"gap anchor x{src.count(OLD_GAP)}"

out = src.replace(OLD_DOC, NEW_DOC, 1).replace(OLD_CALL, NEW_CALL, 1).replace(OLD_GAP, NEW_GAP, 1)
assert '"kind": "player"' not in out, "a player claim survived"
io.open(P, "w", encoding="utf-8").write(out)
print(f"{P}: kind is now tactics|unknown, never player")
