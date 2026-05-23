# Data Directory

This directory is intentionally kept lightweight.

`context_cache.db` is not included in the repository. The best-performing
SpatialAgent configuration uses this optional SQLite cache to avoid repeated
Google Maps API calls and to make benchmark runs more stable.

Build a local cache:

```bash
python data/build_cache.py \
  --input examples/cache_input_sample.jsonl \
  --output data/context_cache.db
```

For benchmark use, obtain `MapEval-Textual.jsonl` from the official
MapEval-Textual dataset:

https://huggingface.co/datasets/MapEval/MapEval-Textual

The dataset is associated with the ICML 2025 paper *MapEval: A Map-Based
Evaluation of Geo-Spatial Reasoning in Foundation Models*:

https://openreview.net/forum?id=hS2Ed5XYRq

Export the Hugging Face split to JSONL:

```bash
pip install datasets

python - <<'PY'
from datasets import load_dataset

ds = load_dataset("MapEval/MapEval-Textual", name="benchmark", split="test")
ds.to_json("MapEval-Textual.jsonl", orient="records", lines=True, force_ascii=False)
PY
```

Then build the real local cache:

```bash
python data/build_cache.py \
  --input MapEval-Textual.jsonl \
  --output data/context_cache.db
```

Do not commit generated cache files, deduplication logs, or benchmark reports.
