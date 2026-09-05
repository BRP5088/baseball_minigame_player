"""A reference frame REPLACED IN PLACE must be seen. And add() must not
overwrite a reference that is still on disk.

WHY THIS EXISTS
---------------
places._feat_cache was keyed on the FILE PATH with no stamp and no
invalidation, so the first read of a reference won for the life of the
process. Measured on the real localiser before the fix, alpha/000.jpg replaced
in place with a third room's frame:

    before swap   identify(C) -> (None, 108, 1.89)
    after  swap   identify(C) -> (None, 108, 1.89)   IDENTICAL
    after  swap   identify(A) -> ('alpha', 1500, 16.48)

The process kept answering from a picture that was no longer on disk, and
nothing anywhere said so. That is not hypothetical here: three of the four
route references were swapped in place on 2026-09-03, and
graph_walk.REFERENCE_POSE exists to A/B two different reference sets — with a
stale cache that A/B silently measures the SAME set twice, an experiment that
cannot detect its own treatment.

THE THREE CASES BELOW ARE NOT REDUNDANT. Each kills a different weakening of
the stamp, and each is forced deterministically rather than left to timing:

    1. ordinary replace          any stamp catches it
    2. same size, same SECOND    only nanosecond mtime catches it
    3. mtime preserved exactly   only size catches it   (cp -p / rsync / tar)

Case 2 is the mutation-testing lesson from CLAUDE.md turned into a test:
CPython validates a cached .pyc on (mtime, size) at ONE-SECOND resolution, and
that is precisely why same-size edits inside one second ran stale bytecode here
and the mutants never executed.

Case 4 is the positive control, and without it every case above passes just as
happily with the cache DELETED — "never cache anything" is never stale. It
asserts an unchanged file is still served from memory.

The add() cases at the end guard the second half of the same bug: the new
filename came from `len(glob("*.jpg"))`, a COUNT, so a gap in the numbering
made the next add OVERWRITE a reference still in use — and the overwritten
path was then served from the stale cache above. Two of those cases came from
brute-forcing 386 directory states rather than from imagination; one of them
("a differently padded stem") killed a mutant I had wrongly convinced myself
was equivalent.

Offline. Reads reference frames already on disk, writes only to a temp
directory; nothing here touches places/, world_map.json, or the console.
"""
import glob
import os
import os as _os
import shutil
import sys
import tempfile

os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)

import places

fails = []


def check(c, m):
    if not c:
        fails.append(m)


# Three DIFFERENT rooms' reference frames, used as three distinguishable
# pictures. Real frames, because ORB on a synthetic image is not the thing
# under test.
def _pick(room):
    got = sorted(glob.glob(os.path.join(_ROOT, "places", room, "*.jpg")))
    return got[0] if got else None


A, B, C = (_pick("portrait_room"), _pick("bar_jukebox"),
           _pick("bar_pool_room"))
check(all((A, B, C)), "need three reference frames on disk to run this test")
if not all((A, B, C)):
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)

_BYTES = {p: open(p, "rb").read() for p in (A, B, C)}


def _probe_case_insensitive():
    """Does this filesystem treat 002.jpg and 002.JPG as the same file?

    Asked rather than assumed, because one add() case below only has something
    to catch when the answer is yes, and would fail on the filesystem rather
    than on the code when it is no.
    """
    d = tempfile.mkdtemp(prefix="places_case_")
    try:
        open(os.path.join(d, "ZZ_PROBE.jpg"), "wb").close()
        return os.path.exists(os.path.join(d, "zz_probe.jpg"))
    finally:
        shutil.rmtree(d, ignore_errors=True)


_CASE_INSENSITIVE = _probe_case_insensitive()


def _write(path, src, size=None):
    """Write `src`'s bytes to `path`, padded to `size` if given.

    A JPEG decoder stops at the EOI marker, so trailing NULs let two different
    pictures be written at IDENTICAL byte sizes — which is what case 2 needs.
    """
    raw = _BYTES[src]
    if size is not None:
        check(len(raw) <= size, f"cannot pad {src} down to {size}")
        raw = raw + b"\x00" * (size - len(raw))
    with open(path, "wb") as f:
        f.write(raw)


def _fresh(first, size=None):
    """A places root: alpha/000.jpg = `first`, beta/000.jpg = B."""
    root = tempfile.mkdtemp(prefix="places_cache_")
    for room in ("alpha", "beta"):
        os.makedirs(os.path.join(root, room))
    tgt = os.path.join(root, "alpha", "000.jpg")
    _write(tgt, first, size)
    _write(os.path.join(root, "beta", "000.jpg"), B)
    return root, tgt


def _swap_case(label, size=None, keep_mtime=False, same_second=False):
    """alpha holds A; identify(A) names it. Replace alpha with C in place;
    identify(C) must now name alpha, and identify(A) must stop naming it."""
    root, tgt = _fresh(A, size)
    before_c = places.identify(C, root=root)
    before_a = places.identify(A, root=root)
    check(before_a[0] == "alpha",
          f"{label}: setup is broken — identify(A) said {before_a} before the "
          f"swap, so the test cannot show a swap being noticed")
    check(before_c[0] is None,
          f"{label}: setup is broken — identify(C) said {before_c} before C "
          f"was ever written to disk")

    st = os.stat(tgt)
    _write(tgt, C, size)
    if keep_mtime:
        os.utime(tgt, ns=(st.st_mtime_ns, st.st_mtime_ns))
        check(os.stat(tgt).st_mtime_ns == st.st_mtime_ns,
              f"{label}: could not force an identical mtime, so this case is "
              f"not testing what it claims")
        check(os.stat(tgt).st_size != st.st_size,
              f"{label}: sizes are equal too — nothing distinguishes the "
              f"versions and the case is vacuous")
    if same_second:
        sec = (st.st_mtime_ns // 1_000_000_000) * 1_000_000_000
        ns = sec + 123_456_789
        ns = ns + 1 if ns == st.st_mtime_ns else ns
        os.utime(tgt, ns=(ns, ns))
        now = os.stat(tgt)
        check(now.st_mtime_ns != st.st_mtime_ns
              and int(now.st_mtime) == int(st.st_mtime),
              f"{label}: could not force a same-second, different-nanosecond "
              f"mtime, so this case is not testing what it claims")
        check(now.st_size == st.st_size,
              f"{label}: sizes differ ({st.st_size} -> {now.st_size}), so "
              f"size alone would catch this and the case is vacuous")

    after_c = places.identify(C, root=root)
    after_a = places.identify(A, root=root)
    check(after_c[0] == "alpha",
          f"{label}: after replacing alpha's reference with C IN PLACE, "
          f"identify(C) said {after_c} — the cache is still serving the old "
          f"descriptors, so the file on disk is not what the localiser sees")
    check(after_a[0] != "alpha",
          f"{label}: identify(A) still said {after_a} after A was overwritten "
          f"on disk — a room answering with a picture that no longer exists")
    shutil.rmtree(root, ignore_errors=True)


_swap_case("plain replace")
_swap_case("same size, same second", size=max(len(_BYTES[A]), len(_BYTES[C])),
           same_second=True)
_swap_case("mtime preserved exactly", keep_mtime=True)


# ---- POSITIVE CONTROL: an UNCHANGED file must still be served from cache ----
# Without this, deleting the cache outright passes every case above.
root, tgt = _fresh(A)
places.identify(A, root=root)                      # warm
_real_as_gray = places._as_gray


def _explode(img):
    # Only the REFERENCE frames are cached; the query frame is computed every
    # call by design, so it must still be allowed through.
    if isinstance(img, str) and os.path.abspath(img).startswith(root):
        raise AssertionError(
            f"recomputed {os.path.basename(img)}, whose file never changed")
    return _real_as_gray(img)


places._as_gray = _explode
try:
    again = places.identify(A, root=root)
    check(again[0] == "alpha",
          f"cache hit path returned {again}, not the room it returned when "
          f"the features were computed")
except AssertionError as e:
    check(False, f"the cache is not being used at all: {e}")
finally:
    places._as_gray = _real_as_gray
shutil.rmtree(root, ignore_errors=True)


# ---- add() must never overwrite a reference that is still on disk ----------
# The old name was len(glob("*.jpg")) — a COUNT, with no relation to the
# highest index in use. Any GAP in the numbering makes it name a file that
# already exists; the non-numbered frames every real room holds (route_*.jpg,
# live_*.jpg) shift the count again, sometimes hiding the collision.
def _add_case(label, existing, delete=()):
    root = tempfile.mkdtemp(prefix="places_add_")
    d = os.path.join(root, "alpha")
    os.makedirs(d)
    for n in existing:
        _write(os.path.join(d, n), A)
    for n in delete:
        os.remove(os.path.join(d, n))
    before = {p: os.path.getsize(p) for p in glob.glob(os.path.join(d, "*"))}
    written = places.add("alpha", C, root=root)
    check(written not in before,
          f"{label}: add() wrote {os.path.basename(written)}, which already "
          f"existed — a reference was OVERWRITTEN, and load_keypoints() still "
          f"finds the filename so nothing reports it missing")
    survived = {p: os.path.getsize(p) for p in glob.glob(os.path.join(d, "*"))}
    # Name-independent, and the only check that catches a clobber through a
    # DIFFERENT directory entry: on a case-insensitive filesystem, writing
    # "002.jpg" overwrites an existing "002.JPG" while the entry keeps its
    # original name, so comparing filenames alone sees nothing wrong.
    check(len(survived) == len(before) + 1,
          f"{label}: the room held {len(before)} files and holds "
          f"{len(survived)} after adding one — a frame was overwritten, not "
          f"added")
    for p, n in before.items():
        check(survived.get(p) == n,
              f"{label}: {os.path.basename(p)} changed size {n} -> "
              f"{survived.get(p)}; add() clobbered an existing reference")
    check(os.path.exists(written), f"{label}: add() returned a missing path")
    # NAMES ARE NEVER REUSED. A deleted 001.jpg must not come back meaning a
    # different picture: notes, logs and the map refer to references by
    # filename, and an index that cycles makes two frames share a name across
    # time. This is what the highest-stem+1 buys over simply looping up from
    # zero, which would silently refill a gap.
    stems = [int(os.path.splitext(os.path.basename(q))[0])
             for q in before
             if os.path.splitext(os.path.basename(q))[0].isdigit()]
    got = os.path.splitext(os.path.basename(written))[0]
    if stems and got.isdigit():
        check(int(got) > max(stems),
              f"{label}: add() wrote {got}.jpg, at or below the highest index "
              f"already used ({max(stems)}) — a name that once meant another "
              f"frame is being reused")
    shutil.rmtree(root, ignore_errors=True)


# The first two collide outright under the old count-based name. The rest each
# pin one property that no single guard provides on its own: an index above
# every one already used, and a name checked against the filesystem rather
# than against what the glob happened to return.
_add_case("a deleted frame", ["000.jpg", "001.jpg", "002.jpg"],
          delete=["001.jpg"])
_add_case("a gap in the numbering", ["000.jpg", "002.jpg"])
_add_case("a gap far below the highest index", ["000.jpg", "005.jpg"])
# A stem padded to a different width: "0007.jpg" already claims index 7, but
# the FILE "007.jpg" does not exist, so an index derived from the highest stem
# without the +1 lands on a free name that duplicates an index already in use.
# Found by brute-forcing 386 directory states against the two forms; the case
# was not one I would have thought of.
_add_case("a differently padded stem", ["000.jpg", "0007.jpg"])
_add_case("non-numbered frames present",
          ["000.jpg", "route_0038.23.jpg", "live_00.jpg"])
# glob("*.jpg") does NOT match "002.JPG", but on a case-INSENSITIVE filesystem
# os.path.exists("002.jpg") is True and saving there overwrites it under a
# directory entry with a different name. Probed rather than assumed: on a
# case-sensitive volume the two agree, the guard is unreachable, and the case
# would fail for a reason that is about the filesystem and not the code. The
# skip is printed, never silent.
if _CASE_INSENSITIVE:
    _add_case("an uppercase extension the glob cannot see",
              ["000.jpg", "001.jpg", "002.JPG"])
else:
    print("  [skipped] uppercase-extension case — this filesystem is "
          "CASE-SENSITIVE, so glob and os.path.exists agree and the collision "
          "it exercises cannot happen here")
_add_case("empty room", [])

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print("  reference cache: an in-place swap is seen (plain, same-size/"
      "same-second, and mtime-preserved), an unchanged file is still cached, "
      "and add() never overwrites an existing reference")
