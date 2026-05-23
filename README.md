# SpatialAgent

SpatialAgent is a research codebase for answering spatial reasoning questions with
an LLM-driven planning pipeline, geospatial operators, and an optional local
context cache.

This repository is a clean open-source candidate derived from the best local
agent implementation. It intentionally excludes private reports, local logs,
paper PDFs, notebooks, and prebuilt SQLite cache files.

## Features

- Intent routing for nearby, routing, trip, and POI-style questions.
- LLM-generated transformation plans over spatial operators.
- Local SQLite context cache support for faster and more reliable evaluation.
- Google Maps API fallback for cache misses.
- Batch evaluation script for MapEval-style multiple-choice questions.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file from `.env.example`:

```bash
cp .env.example .env
```

Then fill in your own API keys.

## Quick Start

Interactive mode:

```bash
python main.py
```

Run a small evaluation file:

```bash
python test_agent.py --dataset-file examples/mapeval_api_sample.jsonl --ids 1
```

## Local Context Cache

The strongest results depend on a local SQLite context cache at:

```text
data/context_cache.db
```

The cache is not included in this repository. It may contain API-derived place,
route, travel-time, or nearby-place content, so users should build it themselves
from data they are allowed to use.

Build a cache from a MapEval-Textual-style JSONL file:

```bash
python data/build_cache.py \
  --input examples/cache_input_sample.jsonl \
  --output data/context_cache.db
```

### MapEval Data

For real benchmark runs, use the official MapEval datasets from Hugging Face:

- MapEval-Textual: https://huggingface.co/datasets/MapEval/MapEval-Textual
- MapEval-API: https://huggingface.co/datasets/MapEval/MapEval-API

`MapEval-Textual.jsonl` is used to build `data/context_cache.db` because it
contains the `context` field with place information, routes, travel times, and
nearby-place lists. `MapEval-API.jsonl` is used by `test_agent.py` for
evaluation because it contains the multiple-choice questions without the
textual context.

One way to export the Hugging Face dataset to the JSONL format expected by this
project is:

```bash
pip install datasets

python - <<'PY'
from datasets import load_dataset

textual = load_dataset("MapEval/MapEval-Textual", name="benchmark", split="test")
textual.to_json("MapEval-Textual.jsonl", orient="records", lines=True, force_ascii=False)

api = load_dataset("MapEval/MapEval-API", name="benchmark", split="test")
api.to_json("MapEval-API.jsonl", orient="records", lines=True, force_ascii=False)
PY
```

Then build the local cache:

```bash
python data/build_cache.py \
  --input MapEval-Textual.jsonl \
  --output data/context_cache.db
```

The generated `MapEval-*.jsonl`, `data/context_cache.db`, and
`data/dedup_log.txt` files are ignored by git. They are intended for local
benchmarking, not for source release.

If you use the MapEval data, cite the original paper:

```bibtex
@inproceedings{dihan2025mapeval,
  title={MapEval: A Map-Based Evaluation of Geo-Spatial Reasoning in Foundation Models},
  author={Mahir Labib Dihan and MD Tanvir Hassan and MD TANVIR PARVEZ and Md Hasebul Hasan and Md Almash Alam and Muhammad Aamir Cheema and Mohammed Eunus Ali and Md Rizwan Parvez},
  booktitle={Forty-second International Conference on Machine Learning},
  year={2025}
}
```

## Repository Contents

- `src/agent/`: routing, planning, execution, and answer generation.
- `src/tools/`: Google Maps wrapper, context parsing, local SQLite cache.
- `src/utils/`: logging and spatial optimization utilities.
- `data/build_cache.py`: builds the optional SQLite cache.
- `test_agent.py`: MapEval-style batch evaluator.
- `examples/`: small synthetic files for smoke tests only.

## Privacy And Data Policy

This candidate release does not include:

- API keys or `.env` files.
- Local SQLite cache files.
- Deduplication logs.
- Generated reports or runtime logs.
- Paper PDFs, notebooks, PPTX/XLSX files, or private research notes.

## License

MIT License.
