# The local-OCR bake-off models — removed 2026-09-17, and how to get them back

`armor_venv/` (601M) and `models/` (23G) were deleted at the user's instruction:
*"Remove armor. It was used to test a new OCR method. While it worked really well,
it wasn't fast enough to use"* and *"Worst case scenario, we reinstall them."*

**This file exists because "worst case we reinstall" was only true if the pointer
survived the deletion, and it very nearly did not.** The upstream identity and the
pinned commit of every model lived in exactly one place — inside the trees being
deleted (`models/<X>/README.md` and
`models/<X>/.cache/huggingface/download/*.metadata`). Nothing outside `models/`
named a single one of them. An adversarial check found that before the `rm`, which
is the only reason this file has SHAs in it.

## The pins

Verified by reading each tree before deletion. The SHA is the commit that was
actually downloaded, so these reinstall the exact weights that were benchmarked,
not whatever HEAD is today.

| directory | size | pinned commit | upstream (see caveat) |
|---|---|---|---|
| `ArmorOCR` | 16G | `569a1c381c78d06f9da6555575a4db690b5a0b90` | `ant-research/ArmorOCR` |
| `typhoon-ocr1.5-2b` | 4.0G | `15b381a2d62569e6736f9c085859dff68e48608d` | `scb10x/typhoon-ocr1.5-2b` |
| `surya-ocr-2-gguf` | 1.4G | `6a3a4c30e5e74446d4f8b6afd05b2f2da970f470` | `datalab-to/...` |
| `GOT-OCR-2.0-hf` | 1.1G | `d3017ef2c2c1395888c8d635c5e0508bcb0ac78d` | `stepfun-ai/GOT-OCR-2.0-hf` |

**ESTABLISHED** — the directory names and the four SHAs, read directly off the
download metadata.

**ASSUMED, and say so before quoting it** — the HuggingFace repo ids. Only the
GitHub project was stated outright in each README (`ant-research/ArmorOCR`,
`Ucas-HaoranWei/GOT-OCR2.0`, `datalab-to/chandra` + `datalab-to/marker`,
`scb-10x/typhoon-ocr`); the HF org was inferred from it. `surya-ocr-2-gguf`'s owner
appeared NOWHERE on disk, in or out of `models/`, so its row is the weakest.
Resolve by searching the name on huggingface.co and checking the SHA matches.

Base models, from the READMEs: ArmorOCR and typhoon-ocr1.5-2b are both Qwen3-VL
(8B and 2B Instruct respectively).

## Do not reinstall these to read the hand

`local_hand.py`'s opening docstring carries the bake-off that retired them, on the
same 22 hands:

    Apple Vision        2 of 8 digits      49 ms
    Apple Vision x6     3 of 8            480 ms
    GOT-OCR-2.0         "2222222222"      8.2 s
    PaddleOCR           none             33   s
    ArmorOCR            read them well    9.9 s
    the shipped reader  5600 / 5600        ~2 ms   template match, no model

They are all TEXT LINE recognisers and a lone digit in a circle offers them no
line. ArmorOCR is the one worth remembering: it was ACCURATE and still useless,
because 9.9 s cannot serve a loop that polls at 150 ms. Accuracy was never the
binding constraint.

The per-model result files survive in `agent_progress/bakeoff/` —
`armor_results.json`, `got2_results.json`, `typhoon_results.json`,
`applevision_results.json`, `incumbent_results.json`, `score.json` — but that
directory is gitignored and CLAUDE.md calls it safe to delete wholesale, so treat
the docstring above as the durable record and those files as convenience.

## What the deletion broke, deliberately

`agent_progress/bakeoff/run_armor.py` and `run_hf_model.py` load weights from
`models/` and are launched with `armor_venv/bin/python`. They can no longer run.
Nothing invokes them — no runner, no test, no hook — and `.venv` could not run
them anyway: `requirements.txt` has zero entries for torch, transformers, onnx,
huggingface or accelerate. Re-running the bake-off means restoring both the venv
and the weights, which is what this file is for.
