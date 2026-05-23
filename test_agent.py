#!/usr/bin/env python3
"""Batch evaluator for SpatialAgent on MapEval-style multiple-choice data."""

import argparse
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from src.agent.spatial_agent import create_spatial_agent

TARGET_CLASSES = {"nearby", "routing", "trip", "poi"}


def load_all_datasets(dataset_file: str = "MapEval-API.jsonl") -> List[Dict[str, Any]]:
    """Load MapEval-style JSONL and keep supported classes only."""
    rows: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {}

    print("=" * 80)
    print("Loading dataset")
    print("=" * 80)
    print(f"File: {dataset_file}")
    print(f"Target classes: {', '.join(sorted(TARGET_CLASSES))}")
    print()

    if not os.path.exists(dataset_file):
        print(f"Error: dataset file not found: {dataset_file}")
        return rows

    with open(dataset_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"Warning: line {line_num} is not valid JSON: {exc}")
                continue

            classification = item.get("classification")
            if classification not in TARGET_CLASSES:
                continue

            answer = item.get("answer")
            if not isinstance(answer, int):
                print(f"Warning: line {line_num} has no integer answer; skipped")
                continue

            converted = {
                "id": item["id"],
                "question": item["question"],
                "answer": {
                    "options": item["options"],
                    "correct": answer - 1,
                },
                "classification": classification,
            }
            rows.append(converted)
            counts[classification] = counts.get(classification, 0) + 1

    print("Loaded samples:")
    for cls in sorted(counts):
        print(f"  {cls:10s}: {counts[cls]:3d}")
    print(f"\nTotal: {len(rows)} samples")
    print("=" * 80)
    print()
    return rows


def filter_by_intents(dataset: List[Dict[str, Any]], intents: Optional[List[str]]) -> List[Dict[str, Any]]:
    """Filter the dataset by classification labels."""
    if not intents:
        return dataset
    intent_set = {intent.strip() for intent in intents if intent.strip()}
    filtered = [item for item in dataset if item.get("classification") in intent_set]
    print(f"Intent filter: {', '.join(sorted(intent_set))}")
    print(f"Matched samples: {len(filtered)}")
    print()
    return filtered


def build_id_mapping(dataset: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """Build an id-to-sample lookup."""
    return {int(item["id"]): item for item in dataset}


def parse_ids(raw: str) -> List[int]:
    """Parse comma- or whitespace-separated sample ids."""
    ids: List[int] = []
    for token in re.split(r"[\s,]+", raw.strip()):
        if not token:
            continue
        try:
            ids.append(int(token))
        except ValueError:
            print(f"Warning: could not parse id: {token}")
    return ids


def stratified_sample(dataset: List[Dict[str, Any]], ratio: float, seed: int) -> List[Dict[str, Any]]:
    """Sample each class independently with a stable random seed."""
    rng = random.Random(seed)
    by_class: Dict[str, List[Dict[str, Any]]] = {}
    for item in dataset:
        by_class.setdefault(item.get("classification", "unknown"), []).append(item)

    samples: List[Dict[str, Any]] = []
    print("Stratified sampling")
    print(f"Ratio: {ratio:.2f}, seed: {seed}")
    for cls, items in sorted(by_class.items()):
        n = max(1, int(round(len(items) * ratio)))
        selected = rng.sample(items, min(n, len(items)))
        samples.extend(selected)
        print(f"  {cls:10s}: {len(selected):3d}/{len(items):3d}")
    print(f"Total selected: {len(samples)}")
    print()
    return samples


def test_single(agent: Any, item: Dict[str, Any], index: int, total: int) -> Dict[str, Any]:
    """Run one sample through SpatialAgent and return a normalized result row."""
    question_id = item.get("id")
    question = item.get("question", "")
    expected_cls = item.get("classification")
    options = item.get("answer", {}).get("options", [])
    correct_answer = item.get("answer", {}).get("correct")
    correct_text = None
    if isinstance(correct_answer, int) and 0 <= correct_answer < len(options):
        correct_text = str(options[correct_answer]).strip()

    start_time = time.time()
    try:
        result = agent.process_question(
            question,
            options=options,
            correct_answer=correct_answer,
            question_id=question_id,
        )
        elapsed = time.time() - start_time

        predicted_intent = result.get("intent")
        predicted_option = result.get("predicted_option")
        predicted_answer = result.get("predicted_answer")
        error = result.get("error")

        intent_correct = predicted_intent == expected_cls
        answer_correct = False
        if predicted_answer is not None and correct_text is not None:
            answer_correct = predicted_answer.strip().lower() == correct_text.lower()
        elif predicted_option is not None and correct_answer is not None:
            answer_correct = predicted_option == correct_answer

        intent_mark = "OK" if intent_correct else "NO"
        answer_mark = "OK" if answer_correct else "NO"
        shown_pred = predicted_answer if predicted_answer is not None else f"idx={predicted_option}"
        shown_correct = correct_text if correct_text is not None else f"idx={correct_answer}"
        print(
            f"[{index}/{total}] ID {question_id:3d} | "
            f"{expected_cls:10s} -> {predicted_intent or 'None':10s} {intent_mark} | "
            f"pred={str(shown_pred)[:24]!r}, correct={str(shown_correct)[:24]!r} {answer_mark} | "
            f"{elapsed:.1f}s"
        )

        return {
            "id": question_id,
            "question": question,
            "expected_classification": expected_cls,
            "predicted_intent": predicted_intent,
            "correct_answer": correct_answer,
            "correct_answer_text": correct_text,
            "predicted_option": predicted_option,
            "predicted_answer": predicted_answer,
            "intent_correct": intent_correct,
            "answer_correct": answer_correct,
            "time": elapsed,
            "error": error,
        }
    except Exception as exc:
        elapsed = time.time() - start_time
        print(f"[{index}/{total}] ID {question_id:3d} | ERROR: {str(exc)[:80]} | {elapsed:.1f}s")
        return {
            "id": question_id,
            "question": question,
            "expected_classification": expected_cls,
            "predicted_intent": None,
            "correct_answer": correct_answer,
            "correct_answer_text": correct_text,
            "predicted_option": None,
            "predicted_answer": None,
            "intent_correct": False,
            "answer_correct": False,
            "time": elapsed,
            "error": str(exc),
        }


def test_batch(agent: Any, samples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Evaluate a batch of samples."""
    results = []
    total = len(samples)
    print("=" * 80)
    print(f"Running evaluation on {total} samples")
    print("=" * 80)
    for index, item in enumerate(samples, 1):
        results.append(test_single(agent, item, index, total))
    print()
    return results


def calculate_statistics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate aggregate and per-class accuracy statistics."""
    total = len(results)
    intent_correct = sum(1 for row in results if row.get("intent_correct"))
    answer_correct = sum(1 for row in results if row.get("answer_correct"))
    failed = [row["id"] for row in results if row.get("error")]

    by_intent: Dict[str, Dict[str, Any]] = {}
    for row in results:
        cls = row.get("expected_classification", "unknown")
        stats = by_intent.setdefault(cls, {"total": 0, "correct": 0})
        stats["total"] += 1
        if row.get("answer_correct"):
            stats["correct"] += 1

    for stats in by_intent.values():
        stats["accuracy"] = round(stats["correct"] / stats["total"], 4) if stats["total"] else 0.0

    avg_time = sum(row.get("time", 0.0) for row in results) / total if total else 0.0
    return {
        "intent_classification_accuracy": {
            "correct": intent_correct,
            "total": total,
            "accuracy": round(intent_correct / total, 4) if total else 0.0,
        },
        "answer_accuracy_by_intent": by_intent,
        "overall_answer_accuracy": {
            "correct": answer_correct,
            "total": total,
            "accuracy": round(answer_correct / total, 4) if total else 0.0,
        },
        "performance": {
            "average_time_seconds": round(avg_time, 3),
            "failed_count": len(failed),
            "failed_ids": failed,
        },
    }


def generate_report(
    results: List[Dict[str, Any]],
    statistics: Dict[str, Any],
    metadata: Dict[str, Any],
    output_dir: str,
) -> str:
    """Write a JSON evaluation report."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = Path(output_dir) / f"test_{timestamp}.json"
    payload = {"metadata": metadata, "statistics": statistics, "results": results}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return str(path)


def print_summary(statistics: Dict[str, Any]) -> None:
    """Print a concise evaluation summary."""
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    intent = statistics["intent_classification_accuracy"]
    overall = statistics["overall_answer_accuracy"]
    perf = statistics["performance"]
    print(f"Intent accuracy: {intent['correct']}/{intent['total']} ({intent['accuracy'] * 100:.1f}%)")
    print("Answer accuracy by intent:")
    for cls, stats in sorted(statistics["answer_accuracy_by_intent"].items()):
        print(f"  {cls:10s}: {stats['correct']:3d}/{stats['total']:3d} ({stats['accuracy'] * 100:.1f}%)")
    print(f"Overall answer accuracy: {overall['correct']}/{overall['total']} ({overall['accuracy'] * 100:.1f}%)")
    print(f"Average time: {perf['average_time_seconds']:.2f}s")
    if perf["failed_count"]:
        print(f"Failed samples: {perf['failed_ids']}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SpatialAgent batch evaluator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_agent.py --ids 357,334,479
  python test_agent.py --stratified 0.3 --seed 42
  python test_agent.py --full
  python test_agent.py --dataset-file examples/mapeval_api_sample.jsonl --ids 1
""",
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--ids", type=str, help="Comma- or whitespace-separated sample ids")
    mode_group.add_argument("--stratified", type=float, metavar="RATIO", help="Stratified sampling ratio")
    mode_group.add_argument("--full", action="store_true", help="Evaluate the full dataset")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for stratified sampling")
    parser.add_argument("--dataset-file", type=str, default="MapEval-API.jsonl", help="Input JSONL dataset")
    parser.add_argument("--output-dir", type=str, default="reports", help="Report output directory")
    parser.add_argument("--intents", type=str, default=None, help="Optional comma-separated class filter")
    args = parser.parse_args()

    dataset = load_all_datasets(args.dataset_file)
    if args.intents:
        dataset = filter_by_intents(dataset, args.intents.split(","))
    if not dataset:
        print("Error: no samples available after loading and filtering")
        sys.exit(1)

    if args.ids:
        id_mapping = build_id_mapping(dataset)
        wanted_ids = parse_ids(args.ids)
        missing = [sample_id for sample_id in wanted_ids if sample_id not in id_mapping]
        if missing:
            print(f"Warning: ids not found: {missing}")
        samples = [id_mapping[sample_id] for sample_id in wanted_ids if sample_id in id_mapping]
        test_mode = "ids"
        sample_ratio = None
        random_seed = None
    elif args.stratified:
        if not (0.0 < args.stratified <= 1.0):
            print("Error: --stratified must be in the range (0.0, 1.0]")
            sys.exit(1)
        samples = stratified_sample(dataset, args.stratified, args.seed)
        test_mode = "stratified"
        sample_ratio = args.stratified
        random_seed = args.seed
    else:
        samples = dataset
        test_mode = "full"
        sample_ratio = None
        random_seed = None
        print(f"Selected all {len(samples)} samples")
        print()

    if not samples:
        print("Error: no selected samples")
        sys.exit(1)

    print("Initializing SpatialAgent...")
    try:
        agent = create_spatial_agent()
    except Exception as exc:
        print(f"Error: agent initialization failed: {exc}")
        print("Check API keys, dependencies, and network access.")
        sys.exit(1)
    print("Agent initialized successfully.")
    print()

    results = test_batch(agent, samples)
    statistics = calculate_statistics(results)
    metadata = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "test_mode": test_mode,
        "sample_ratio": sample_ratio,
        "random_seed": random_seed,
        "total_samples": len(samples),
        "dataset_source": args.dataset_file,
    }
    report_path = generate_report(results, statistics, metadata, args.output_dir)
    print_summary(statistics)
    print(f"Report saved to: {report_path}")


if __name__ == "__main__":
    main()
