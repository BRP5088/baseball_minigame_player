#!/bin/bash
# Undo the Phase 1 reference swap. Step 3 (re-measure align_lateral) was NOT
# run, so these references are UNVALIDATED.
set -e
cd "$(dirname "$0")/.."
for d in places_backup_20260903_020639/*/; do
  n=$(basename "$d")
  [ "$n" = "manifest.json" ] && continue
  cp -v "$d"route_*.jpg "places/$n/"
done
echo "reverted to the human-walk references"
