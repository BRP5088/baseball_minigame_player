#!/bin/bash
# Stop chiaki, install a fresh build, re-sign it, relaunch with injection.
#
# THE TWO THINGS THIS EXISTS TO PREVENT, both learned the hard way:
#
#   1. NEVER cp over a RUNNING binary. macOS validates code-signature pages
#      lazily against the file on disk, so overwriting the image under a live
#      process kills it with "Code Signature Invalid" — and the *next* launch
#      dies the same way, with an empty log and a crash dialog that blocks
#      everything until it is dismissed. Quit first, always.
#
#   2. ALWAYS re-sign after copying. A plain cp does not carry a valid
#      signature for the new contents; the ad-hoc signature below is what makes
#      the copied binary launchable at all.
#
# chiaki also IGNORES SIGTERM while streaming, so stopping it means Cmd+Q and
# then SIGKILL as a fallback.
set -e
DEST="$(cd "$(dirname "$0")" && pwd)/chiaki-ng-build/chiaki.app/Contents/MacOS/chiaki"
# The source tree lives in the PROJECT now, not /tmp — /tmp was found emptied
# on 2026-09-03 (825 directories, zero files), which is what destroyed the
# original checkout. See "Rebuilding chiaki-ng" in CLAUDE.md.
SRC="${1:-$(cd "$(dirname "$0")" && pwd)/chiaki-ng-src/build/gui/chiaki.app/Contents/MacOS/chiaki}"

# -x matches the executable name, so this also catches a stock
# /Applications/chiaki-ng.app someone launched by hand. Matching only
# chiaki-ng-build left that one running and fought us for the stream.
for pid in $(pgrep -x chiaki || true); do
    kill -9 "$pid" 2>/dev/null || true
done
sleep 2

if [ -f "$SRC" ] && [ "$SRC" -nt "$DEST" ]; then
    cp "$SRC" "$DEST"
    echo "installed build from $(date -r "$SRC" '+%H:%M:%S')"
fi

codesign -f -s - "$DEST" 2>/dev/null
codesign -v "$DEST" 2>/dev/null && echo "signature valid"

# CHIAKI_FRAME_DUMP turns on the decoded-frame mmap the Python capture reads
# first (frame_dump.py). Without it every capture goes back to grabbing the
# window off the screen, which dies the moment the user switches macOS Spaces.
# A runtime mmap in /tmp is fine: it is recreated on every launch, and
# CLAUDE.md's "nothing that matters goes in /tmp" is about source and findings.
CHIAKI_INJECT_INPUT=/tmp/chiaki_input CHIAKI_FRAME_DUMP=/tmp/chiaki_frame.bin \
    nohup "$DEST" > /tmp/chiaki_run.log 2>&1 &
sleep 8
pgrep -f chiaki-ng-build > /dev/null || { echo "FAILED to start; see /tmp/chiaki_run.log"; exit 1; }
echo "chiaki running as pid $(pgrep -f chiaki-ng-build)"
grep -i inject /tmp/chiaki_run.log || true
# Both halves of the patch announce themselves, and a MISSING line is the whole
# point: an unpatched or half-patched binary launches, prints nothing unusual
# and delivers nothing, which is how this project lost a day to the injector.
grep -i "frame dump" /tmp/chiaki_run.log \
    || echo "WARNING: no 'frame dump' line -- this build has no frame dump, so "\
"every capture will grab the screen and will fail when the window leaves the Space"
