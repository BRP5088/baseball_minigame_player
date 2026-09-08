#!/bin/zsh
SP=/private/tmp/claude-502/-Users-bpatterson-Documents-Claude-Cowork-Personal-Auto-Baseball/e6392fcc-4b59-4ace-b5b6-76c4bf041181/scratchpad/p47
R="/Users/bpatterson/Documents/Claude Cowork Personal/Auto Baseball"
cp "$R/chain_walk.py" "$SP/chain_walk.py"
cp "$R/tests/routing/test_chain_walk.py" "$SP/tests/routing/test_chain_walk.py"
rm -rf "$SP/__pycache__" "$SP/tests/routing/__pycache__"
