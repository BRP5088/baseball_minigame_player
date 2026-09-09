"""patch69 -- run the local hand reader in production, beside vision.

Anchors are asserted for BOTH edits before either file is written (CLAUDE.md 10.19).
"""
import io, os, sys

ORCH = "orchestrator.py"
src = io.open(ORCH, encoding="utf-8").read()

OLD_START = '''    if "hand" in crops:
        # Cross-read the hand with the local PaddleOCR pipeline and print it'''
OLD_END = '''            else:
                print(f"  [local-check] hand: all 5 slots agree with vision")
'''
assert src.count(OLD_START) == 1, f"start anchor x{src.count(OLD_START)}"
assert src.count(OLD_END) == 1, f"end anchor x{src.count(OLD_END)}"
i = src.index(OLD_START)
j = src.index(OLD_END) + len(OLD_END)
assert j > i, "anchors out of order"
old_block = src[i:j]
assert "read_hand_digits" in old_block, "wrong block: no paddle call inside"
assert len(old_block) < 5000, f"block suspiciously large: {len(old_block)}"

HELPER_ANCHOR = "def log_local_read_comparison(state_json: dict):"
assert src.count(HELPER_ANCHOR) == 1, "helper anchor"

NEW_BLOCK = '''    if "hand" in crops:
        # THE LOCAL HAND READER, run beside vision on every sampled turn.
        #
        # It replaces a PaddleOCR subprocess that reloaded its models on every
        # call. Measured on the same 15 corpus hands: 4.5 ms against seconds,
        # 45 of 55 card positions read, and ZERO disagreements with the paid
        # model. It ABSTAINS rather than guessing, so a position it cannot read
        # comes back None and is reported as NOT READ -- never as a value.
        #
        # WHY IT RUNS BESIDE VISION AND NOT INSTEAD OF IT. A tactics card's
        # decision needs its TYPE, not its number: CLAUDE.md section 4 records
        # that only swing and pitch boosts add power, while speed and fielding
        # boosts carry a nonzero bonus that adds NONE. The type is card art
        # this reader does not read, and 14 of the 15 measured hands hold at
        # least one tactics card -- so dropping the vision call today would
        # lose the type on almost every hand and change which card gets played.
        #
        # So every sampled turn records the crop and BOTH readings. Vision's
        # answer is the label, which makes each turn a labelled example of the
        # tactics art the type reader still needs. That is the cheapest
        # possible way to build the corpus: it rides on turns already paid for.
        import local_hand
        vision_hand = {c.get("hand_index"): c for c in (state_json.get("hand") or [])}
        try:
            rows = local_hand.read_hand(crops["hand"])
        except Exception as e:
            print(f"  [local-check] hand: local reader failed ({e})")
            rows = []
        record_local_hand(crops["hand"], rows, state_json.get("hand") or [])

        # ALIGNMENT IS BY POSITION, so it is only valid when the counts match.
        # A missed or invented card shifts every later column by one and would
        # print four spurious disagreements for one real error, which is
        # exactly the noise that made the previous reader's audit unreadable.
        if len(rows) != len(vision_hand):
            print(f"  [local-check] hand: local found {len(rows)} positions, vision "
                  f"{len(vision_hand)} — counts differ, no per-slot comparison")
        else:
            lines = []
            for i, r in enumerate(rows):
                v = vision_hand.get(i)
                if r["kind"] == "tactics" or r["digit"] is None:
                    continue                      # abstained: nothing to disagree with
                if not v or v.get("kind") != "player":
                    lines.append(f"  [local-check] hand[{i}]: local read {r['digit']} "
                                 f"@{r['score']} but vision says "
                                 f"{_describe_vision_card(v)}  <<< DISAGREE")
                elif str(v.get("power")) != str(r["digit"]):
                    lines.append(f"  [local-check] hand[{i}]: local power={r['digit']} "
                                 f"@{r['score']}  vs vision power={v.get('power')}"
                                 f"  <<< DISAGREE")
            read = sum(1 for r in rows if r["digit"] is not None)
            if lines:
                for line in lines:
                    print(line)
            else:
                print(f"  [local-check] hand: {read}/{len(rows)} read locally, "
                      f"all agree with vision")
'''

HELPER = '''# Where each sampled turn's hand crop and both readings are kept. Vision's
# answer is the LABEL, so this directory accumulates labelled tactics art --
# the one thing the local reader still cannot read (see the note below).
# Appended to, never rewritten: a truncating write loses a whole session's
# corpus if the run is interrupted.
LOCAL_HAND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "overnight", "local_hand")


def record_local_hand(crop, rows, vision_cards):
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
        pass


'''

out = src[:i] + NEW_BLOCK + src[j:]
out = out.replace(HELPER_ANCHOR, HELPER + HELPER_ANCHOR, 1)
assert "read_hand_digits" not in out, "paddle call survived"
assert out.count("def record_local_hand") == 1
assert out.count("import local_hand") >= 1
io.open(ORCH, "w", encoding="utf-8").write(out)
print(f"{ORCH}: replaced {len(old_block)} bytes, added helper")
