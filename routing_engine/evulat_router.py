# C:\projects\Mcp_tool_l2\evaluate_router.py
import json
import time
from collections import defaultdict
from pathlib import Path

from routing_engine.decision import system_one_decision


def run_benchmark(dataset_path=None):
    if dataset_path is None:
        dataset_path = Path(__file__).with_name("ground_trooth.json")

    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    correct = 0
    total = len(data)
    if total == 0:
        print("No benchmark data found.")
        return

    latencies = []
    category_stats = defaultdict(lambda: {"total": 0, "correct": 0})
    mismatches = []

    for item in data:
        qid = item["id"]
        query = item["query"]
        expected = item["expected_tool"]

        start = time.perf_counter()
        predicted, score = system_one_decision(query)
        latency = (time.perf_counter() - start) * 1000
        latencies.append(latency)

        category_stats[expected]["total"] += 1

        if predicted == expected:
            correct += 1
            category_stats[expected]["correct"] += 1
        else:
            mismatches.append(
                {
                    "id": qid,
                    "query": query,
                    "expected": expected,
                    "predicted": predicted,
                    "confidence": score,
                }
            )

    accuracy = (correct / total) * 100
    avg_latency = sum(latencies) / len(latencies)

    print("\n" + "=" * 55)
    print(f"BENCHMARK RESULTS: {correct}/{total} ({accuracy:.2f}% Accuracy)")
    print(f"AVERAGE LATENCY:  {avg_latency:.2f} ms / query (CPU)")
    print("=" * 55)

    print("\nPER-CATEGORY ACCURACY:")
    for cat, stats in category_stats.items():
        cat_acc = (stats["correct"] / stats["total"]) * 100
        print(f" - {cat:15}: {stats['correct']}/{stats['total']} ({cat_acc:.1f}%)")

    if mismatches:
        print(f"\nMISMATCHES FOUND ({len(mismatches)}):")
        for m in mismatches[:10]:
            print(
                f" [{m['id']}] '{m['query']}' -> Expected: {m['expected']} | Predicted: {m['predicted']} (Score: {m['confidence']})"
            )
        if len(mismatches) > 10:
            print(f" ... and {len(mismatches) - 10} more.")


if __name__ == "__main__":
    run_benchmark()