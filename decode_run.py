"""Decode the compass bearing from EVERY frame of a recorded run."""
import glob, json, os, sys, time
os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-decode")
from PIL import Image
import compass

d = sys.argv[1]
out = sys.argv[2]
files = sorted(glob.glob(os.path.join(d, "*.jpg")))
res = []
t0 = time.time()
for i, f in enumerate(files):
    try:
        b = compass.read_bearing(Image.open(f))
    except Exception:
        b = None
    res.append({"file": os.path.basename(f), "t": os.path.basename(f)[9:19], "b": b})
    if i % 200 == 0:
        done = sum(1 for r in res if r["b"] is not None)
        print(f"  {i}/{len(files)}  decoded {done}  {time.time()-t0:.0f}s", flush=True)
    json.dump(res, open(out, "w"))
done = sum(1 for r in res if r["b"] is not None)
print(f"  FINISHED {len(files)} frames, {done} decoded ({done/len(files):.0%}) "
      f"in {time.time()-t0:.0f}s", flush=True)
