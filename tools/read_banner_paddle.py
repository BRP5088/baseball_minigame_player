"""PaddleOCR worker. Runs INSIDE paddle_venv (Python 3.11) -- paddlepaddle has no wheel for
the project's 3.14, which is why this is a subprocess at all.

TWO MODES:
  argv paths   read those images, print one JSON object, exit.  (one-shot, for probes)
  no argv      SERVER: load the model ONCE, then read one image path per line on stdin and
               print one JSON line per path, flushed.

The server mode exists because the model load is the whole cost: measured 4.8-6.2 s per
one-shot call against a few hundred ms of actual inference. The project already settled this
shape for tesseract -- ocr_glyphs keeps a live handle at 134 ms first call, 23 ms steady --
so the banner reader keeps a live process for the same reason. It idles for the rest of the
match, which costs nothing but memory.

It prints READY on stdout once the model is up, so the caller can tell "still loading" from
"wedged" -- those look identical otherwise, which is CLAUDE.md 10.1's signature failure.
"""
import sys, json, os, warnings
warnings.filterwarnings("ignore")
os.environ.setdefault("FLAGS_call_stack_level", "0")
from paddleocr import PaddleOCR

_ocr = PaddleOCR(use_textline_orientation=False, lang="en")


def read(p):
    try:
        texts = []
        for page in _ocr.predict(p):
            d = page if isinstance(page, dict) else getattr(page, "res", {})
            for t, s in zip(d.get("rec_texts") or [], d.get("rec_scores") or []):
                texts.append([t, round(float(s), 3)])
        return texts
    except Exception as e:
        return f"ERR {type(e).__name__}: {e}"


if len(sys.argv) > 1:
    print(json.dumps({p: read(p) for p in sys.argv[1:]}))
    sys.exit(0)

print("READY", flush=True)
for line in sys.stdin:
    p = line.strip()
    if not p or p == "QUIT":
        break
    print(json.dumps({p: read(p)}), flush=True)
