#!/bin/zsh
set -e
S="/private/tmp/claude-502/-Users-bpatterson-Documents-Claude-Cowork-Personal-Auto-Baseball/e6392fcc-4b59-4ace-b5b6-76c4bf041181/scratchpad/p44"
R="/Users/bpatterson/Documents/Claude Cowork Personal/Auto Baseball"
rm -rf "$S"
mkdir -p "$S/tests/routing" "$S/overnight" "$S/tools" "$S/probes"
cd "$R"
for f in chain_walk.py chain.py pose.py places.py compass.py table_prompt.py final_approach.py ocr_glyphs.py input_controller.py analog_replay.py ensure_stream.py slow_traverse.py walk_steps.py turn_curve.py; do
  cp "$f" "$S/$f"
done
cp tests/routing/test_chain_walk.py "$S/tests/routing/"
cp overnight/chain_trials.py overnight/_harness.py "$S/overnight/"
cp tools/collision_census.py tools/turn_review.py tools/trial_sheet.py "$S/tools/"
touch "$S/requirements.txt"
if ! grep -q LOST_RESCUE_MAX "$S/chain_walk.py"; then "$R/.venv/bin/python" -B "$R/drafts/pending_after_ab/apply_patch43.py" "$S" >/dev/null; echo "applied patch43"; else echo "patch43 already in the checkout"; fi
echo "scratch rebuilt with patch43"
