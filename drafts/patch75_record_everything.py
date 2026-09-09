"""patch75 -- record EVERY crop a local reader will need, with the paid model's answer.

Each sampled turn already pays for a vision read. That answer is a LABEL for every region
on the screen, not just the hand, and until now only the hand crop was kept. The fields
still blocking the paid call's removal each need their own labelled corpus:

    phase          from the hand card's banner, BATTER or PITCHER. orchestrator derives it
                   from the card NAME, and `name` was not being recorded -- so the reader
                   could only be trained on the 13 archived hands that carry names. A vote
                   across a hand's cards reads it 7 of 13 with ZERO wrong; the bank is the
                   thin part, not the method.
    runners        the user's observation: a base card carries the SAME disc as a hand
                   card, so "is there a card on this base" is a disc-detection question,
                   not an OCR-a-name question. That needs the base crops, which were
                   thrown away.
    discards_left  the DISCARDS dot counter, which lives in the scoreboard crop.
    secondary      the shield, already inside the hand crop.

So this keeps all five gameplay crops and the whole state answer beside them. Disk is not
the constraint (the user has said so); a labelled example that was never saved is.

THE EXISTING KEYS ARE UNCHANGED -- "crop", "local", "vision" keep their exact shape, so
every analysis script written against the 76 hands already on disk still reads them.
"""
import io

P = "orchestrator.py"
s = io.open(P, encoding="utf-8").read()

OLD_FN = '''def record_local_hand(crop, rows, vision_cards):
    """Keep one labelled example. Never raises into the turn loop."""
    try:
        os.makedirs(LOCAL_HAND_DIR, exist_ok=True)
        stamp = time.time_ns()
        name = f"hand_{stamp}.png"
        crop.save(os.path.join(LOCAL_HAND_DIR, name))
        with open(os.path.join(LOCAL_HAND_DIR, "agreement.jsonl"), "a") as f:
            f.write(json.dumps({
                "t": stamp, "crop": name,
                "local": [{"x": r["x"], "kind": r["kind"], "digit": r["digit"],
                           "score": r["score"]} for r in rows],
                "vision": [{"i": c.get("hand_index"), "kind": c.get("kind"),
                            "power": c.get("power"), "secondary": c.get("secondary"),
                            "bonus": c.get("bonus"), "type": c.get("type")}
                           for c in vision_cards],
            }) + "\\n")
    except Exception:
        pass'''
assert s.count(OLD_FN) == 1, f"recorder anchor x{s.count(OLD_FN)}"

NEW_FN = '''# The five gameplay regions, all of which the paid call has just answered for. Saving only
# the hand meant three of the four remaining local readers had no corpus at all.
RECORDED_CROPS = ("hand", "scoreboard", "third_base", "first_base", "second_base")


def record_local_hand(crops, rows, state_json):
    """Keep one labelled example of EVERY gameplay region. Never raises into the turn loop.

    `crops` is the gameplay crop dict and `state_json` the paid model's whole answer, which
    is the LABEL for all of it -- names and phase for the banner reader, runners for the
    base reader, discards_left for the dot counter, secondary for the shield.
    """
    try:
        os.makedirs(LOCAL_HAND_DIR, exist_ok=True)
        stamp = time.time_ns()
        saved = {}
        for region in RECORDED_CROPS:
            img = (crops or {}).get(region)
            if img is None:
                continue
            fname = f"{region}_{stamp}.png"
            img.save(os.path.join(LOCAL_HAND_DIR, fname))
            saved[region] = fname
        cards = state_json.get("hand") or []
        with open(os.path.join(LOCAL_HAND_DIR, "agreement.jsonl"), "a") as f:
            f.write(json.dumps({
                # "crop", "local" and "vision" keep their exact original shape: every
                # analysis script written against the hands already on disk still reads.
                "t": stamp, "crop": saved.get("hand"), "crops": saved,
                "local": [{"x": r["x"], "kind": r["kind"], "digit": r["digit"],
                           "score": r["score"], "type": r.get("type"),
                           "type_score": r.get("type_score")} for r in rows],
                "vision": [{"i": c.get("hand_index"), "kind": c.get("kind"),
                            "name": c.get("name"),
                            "power": c.get("power"), "secondary": c.get("secondary"),
                            "bonus": c.get("bonus"), "type": c.get("type")}
                           for c in cards],
                "state": {"screen": state_json.get("screen"),
                          "phase": state_json.get("phase"),
                          "your_score": state_json.get("your_score"),
                          "opp_score": state_json.get("opp_score"),
                          "discards_left": state_json.get("discards_left"),
                          "batters_used": state_json.get("batters_used"),
                          "runners": state_json.get("runners")},
            }) + "\\n")
    except Exception:
        pass'''

OLD_CALL = '''        record_local_hand(crops["hand"], rows, state_json.get("hand") or [])'''
assert s.count(OLD_CALL) == 1, f"call anchor x{s.count(OLD_CALL)}"
NEW_CALL = '''        record_local_hand(crops, rows, state_json)'''

out = s.replace(OLD_FN, NEW_FN, 1).replace(OLD_CALL, NEW_CALL, 1)
assert "RECORDED_CROPS" in out and out.count("def record_local_hand") == 1
io.open(P, "w", encoding="utf-8").write(out)
print("orchestrator.py: every gameplay crop is now recorded with the paid answer")
