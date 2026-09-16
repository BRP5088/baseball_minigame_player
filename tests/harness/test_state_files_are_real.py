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
os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import

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

# THE LIST ABOVE CHECKS CONTAINERS, NOT CONTENTS, AND THAT IS HOW THE NEXT TWO
# GOT IN. `places` was on it and passed, because `places` itself is a real
# directory -- while `places/places` was a symlink to its own parent, committed
# by the same worktree merge. It made a PHANTOM ROOM: os.listdir(root) enumerated
# `places` as a fifth room with zero references, and shutil.copytree died with
# ELOOP, which truncated tests/routing/test_add_non_disruption.py from 16 tests
# to 4 and an error. `test_fixtures/test_fixtures` was the same shape.
#
# So this half is STRUCTURAL rather than a hand-kept list, because a list is
# exactly what failed: it names no paths and cannot go stale as the tree grows.
walked = 0
for rel in STATE + OPTIONAL:
    root = os.path.join(_ROOT, rel)
    if not os.path.isdir(root):
        continue
    for dirpath, dirnames, filenames in os.walk(root):
        for name in list(dirnames) + filenames:
            walked += 1
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                check(f"{os.path.relpath(full, _ROOT)} is a symlink inside a "
                      f"state directory -> {os.readlink(full)!r}", False)
        # Do not descend INTO a symlinked directory: that is the loop itself.
        dirnames[:] = [d for d in dirnames
                       if not os.path.islink(os.path.join(dirpath, d))]
check(f"walked the state directories ({walked} entries)", walked >= 8)

# AND THE GENERAL CASE: git is what actually carried the damage between
# checkouts, so ask git. A committed symlink resolving inside the repo is the
# worktree accident and nothing else; the repo has legitimately never had one.
try:
    import subprocess
    out = subprocess.run(["git", "ls-files", "-s"], cwd=_ROOT,
                         capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        check(f"git ls-files ran (rc={out.returncode})", False)
    else:
        links = [l.split("\t", 1)[1] for l in out.stdout.splitlines()
                 if l.startswith("120000 ")]
        # Reported by NAME. "there are 2" sends someone hunting; naming them
        # makes the fix a git rm.
        check(f"no tracked symlinks in the repo (found {links})", not links)
        check(f"git listed the tree ({len(out.stdout.splitlines())} paths)",
              len(out.stdout.splitlines()) > 50)
except Exception as e:                                    # noqa: BLE001
    # FAIL rather than skip: an unverifiable claim is not a passing one, and
    # this is the half that catches the damage before it is merged.
    check(f"could not ask git about tracked symlinks ({type(e).__name__}: {e})",
          False)

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
