"""
Local hand-card art identification via CLIP embeddings — a self-populating
cache, same architecture as KNOWN_BAN_ROSTER's learned-entry pattern in
orchestrator.py, applied to hand cards specifically because they never show
a name (confirmed live 2026-08-24 — the game cuts hand cards off at the
screen edge before the name banner renders), so there's nothing to OCR
there the way there is for base runners.

STATUS: built and tested against real screenshots, NOT wired into the live
pipeline. Read before wiring in:

- Well-framed hand cards match cleanly (same-card similarity ~0.97-0.99 vs
  different-card ~0.76-0.92 in testing).
- One tested case (a card at the fan layout's rightmost edge) showed
  genuine position/scale jitter between two manual screenshots taken
  seconds apart, and no matching technique tried (pHash, ORB, template
  matching, CLIP) resolved it. Those screenshots were never run through
  wait_for_screen_to_settle() — there's no guarantee either was captured
  at a stable moment, so this may or may not be a real problem for the
  live pipeline's own captures. Unconfirmed either way; treat any
  match_hand_card() miss as a normal, expected fallback-to-vision case,
  not a bug, especially for the outermost 1-2 hand slots.
- Only identifies WHICH card (name + kind). For player cards that's
  enough — power/secondary are fixed per identity, look them up from
  KNOWN_BAN_ROSTER in orchestrator.py once matched. For tactics cards,
  the bonus value (e.g. Power Swing shows +1/+2/or +3 on different
  instances) is NOT fixed per name and this module can't read it — that
  still needs a separate read. Not attempted here; badge-digit OCR was
  unreliable for reading an unconstrained digit earlier this session, but
  disambiguating among only 3 known possible values for an
  already-identified tactics type is a much narrower problem than that
  was, worth revisiting separately rather than assumed solved.

Threshold is set conservative (0.95) on purpose: a missed match just
costs one vision fallback call (cheap, safe); a wrong confident match
could feed a bad power/secondary into a real play decision (not safe).
"""

import json
import os

import open_clip
import torch
from PIL import Image

CACHE_FILE = "hand_card_embeddings.json"
MATCH_THRESHOLD = 0.95

_model = None
_preprocess = None


def _get_model():
    """Lazy-loaded so importing this module (or just having it present)
    doesn't pay CLIP's load cost until it's actually used."""
    global _model, _preprocess
    if _model is None:
        _model, _, _preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")
        _model.eval()
    return _model, _preprocess


def embed_card_crop(img: Image.Image) -> list:
    """Returns a normalized CLIP embedding for a card crop, as a plain
    list of floats (JSON-serializable)."""
    model, preprocess = _get_model()
    tensor = preprocess(img.convert("RGB")).unsqueeze(0)
    with torch.no_grad():
        feat = model.encode_image(tensor)
        feat /= feat.norm(dim=-1, keepdim=True)
    return feat[0].tolist()


def _cosine(a: list, b: list) -> float:
    return sum(x * y for x, y in zip(a, b))


def load_cache() -> dict:
    """{"card_name": [[embedding], [embedding], ...]} — a name can hold
    multiple reference embeddings, accumulated over repeated sightings,
    so matching improves over time instead of depending on one lucky
    first capture."""
    if not os.path.exists(CACHE_FILE):
        return {}
    with open(CACHE_FILE) as f:
        return json.load(f)


def save_cache(cache: dict):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)


def learn_hand_card(crop_img: Image.Image, name: str):
    """Add a new reference embedding for `name`, confirmed by whatever
    caller already knows the true identity (e.g. a vision read). Call
    this on every cache miss once vision resolves it, so the cache
    grows and future sightings of the same card are more likely to
    match one of several stored instances instead of just one."""
    cache = load_cache()
    cache.setdefault(name, []).append(embed_card_crop(crop_img))
    save_cache(cache)


def match_hand_card(crop_img: Image.Image, threshold: float = MATCH_THRESHOLD):
    """
    Returns (name, similarity) for the best match across every stored
    reference embedding of every known card, or None if nothing clears
    `threshold` — callers should treat None as "fall back to vision",
    not as an error.
    """
    cache = load_cache()
    if not cache:
        return None
    query = embed_card_crop(crop_img)
    best_name, best_score = None, -1.0
    for name, embeddings in cache.items():
        for emb in embeddings:
            score = _cosine(query, emb)
            if score > best_score:
                best_name, best_score = name, score
    if best_score >= threshold:
        return best_name, best_score
    return None
