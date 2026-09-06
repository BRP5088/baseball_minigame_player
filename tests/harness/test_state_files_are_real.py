"""The project's state files must be REGULAR FILES, never symlinks.

WHAT HAPPENED. Recorder work was done in a git worktree so that read-only QA
agents could analyse an untouched main tree at the same time. A worktree has no
gitignored files, so world_map.json, view_bounds.json, camera_fov.json and
places/ were symlinked into it to make the tests runnable. Then `git add -A`
committed the SYMLINKS, and merging that branch replaced the real files in the
main checkout with links pointing at themselves:

    world_map.json -> /.../world_map.json      ELOOP, unreadable

world_map.json is the file every route is planned from. It was broken for about
a minute and restored from git.

WHY A TEST AND NOT A NOTE. The failure is silent at the moment it is created --
`git add -A` says nothing, the merge says nothing, and the symlink resolves
fine inside the worktree where it was made. It only breaks in the checkout that
receives it, and then it breaks everything at once. Nothing else in the suite
reads these files by path in a way that would notice the type.

places/ is included because the localiser reads it, and an ELOOP there makes
every identify() abstain -- which reads exactly like a thin reference set rather
than like a broken path.
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

ok = True


def check(label, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        ok = False


# Files a live run reads or writes, and the directory the localiser reads.
STATE = ["world_map.json", "camera_fov.json", "route3_steps.json",
         "route2_steps.json", "places"]
# These are gitignored per-machine caches: present on the rig, absent on a
# fresh clone. Checked only if they exist.
OPTIONAL = ["view_bounds.json", "compass_scale.json"]

checked = 0
for rel in STATE + OPTIONAL:
    p = os.path.join(_ROOT, rel)
    if not os.path.exists(p):
        if rel in OPTIONAL:
            continue
        check(f"{rel} exists", False)
        continue
    checked += 1
    check(f"{rel} is a real file, not a symlink", not os.path.islink(p))

# ANTI-VACUITY: if the list stopped matching anything, every check above passes
# for free and the guard is decorative.
check(f"the scan actually examined something ({checked} paths)", checked >= 4)

# And the map must still PARSE -- a symlink loop shows up here as an OSError,
# so this is the behavioural half of the same guard.
try:
    m = json.load(open(os.path.join(_ROOT, "world_map.json")))
    n = sum(len(v) for v in m.get("links", {}).values())
    check(f"world_map.json parses and holds its legs ({n})", n >= 5)
except Exception as e:
    check(f"world_map.json parses ({type(e).__name__}: {e})", False)

print("\nall green" if ok else "\nFAILURES above")
sys.exit(0 if ok else 1)
