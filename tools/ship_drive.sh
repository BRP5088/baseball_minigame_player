#!/bin/bash
# Ship one recorded drive to Snoopy and start it reconstructing.
#
# ONE ROOM PER DRIVE, deliberately. A break costs that room and nothing else,
# the directory name carries the room label as ground truth, and Snoopy can be
# working on room one while the next room is still being driven.
#
#   tools/ship_drive.sh overnight/drives/20260906_170000_bar
#
set -u
D="${1:?usage: ship_drive.sh <drive-directory>}"
KEY="$HOME/.ssh/id_ed25519_snoopy"
HOST="Brett@snoopy"
NAME="$(basename "$D")"

[ -d "$D" ] || { echo "no such drive: $D"; exit 1; }
N=$(ls "$D"/*.jpg 2>/dev/null | wc -l | tr -d ' ')
[ "$N" -gt 0 ] || { echo "$NAME holds no frames — refusing to ship an empty drive"; exit 1; }
[ -f "$D/meta.json" ] || echo "  WARNING: no meta.json — headings will be missing"

echo "shipping $NAME ($N frames, $(du -sh "$D" | cut -f1))"
ssh -i "$KEY" -o BatchMode=yes "$HOST" \
  "New-Item -ItemType Directory -Force -Path C:\\baseball\\data\\drives | Out-Null" >/dev/null 2>&1
scp -q -r -i "$KEY" -o BatchMode=yes "$D" "$HOST:C:/baseball/data/drives/" || {
    echo "  copy FAILED — the local drive is untouched, retry when Snoopy is up"; exit 1; }

# Verify the far side really has them. A copy that half-succeeded and a copy that
# worked look identical from here otherwise.
FAR=$(ssh -i "$KEY" -o BatchMode=yes "$HOST" \
  "(Get-ChildItem 'C:\\baseball\\data\\drives\\$NAME' -Filter *.jpg | Measure-Object).Count" \
  2>/dev/null | tr -d '\r' | tail -1)
echo "  local $N frames, Snoopy $FAR"
[ "$FAR" = "$N" ] || { echo "  MISMATCH — not starting reconstruction on a partial copy"; exit 1; }
echo "  verified. Snoopy has the full drive; local copy kept."
