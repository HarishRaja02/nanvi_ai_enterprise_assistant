"""Evaluation script to measure Precision@1 and Precision@5 on messy enterprise search queries."""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, os.getcwd())

from backend.chat.file_search import execute_file_search
from backend.security.authorization import UserAttributes

logger = logging.getLogger(__name__)


def evaluate_queries(queries_path: Path):
    with open(queries_path, "r", encoding="utf-8") as fp:
        eval_queries = json.load(fp)

    user = UserAttributes(user_id="eval-user", tenant_id="default", department="Management", roles=frozenset({"Supervisor"}))

    total = len(eval_queries)
    hits_at_1 = 0
    hits_at_5 = 0

    results = []

    print(f"Running evaluation on {total} test queries...\n")
    print(f"{'ID':<12} | {'Category':<28} | {'P@1':<5} | {'P@5':<5} | {'Query'}")
    print("-" * 80)

    for item in eval_queries:
        qid = item["id"]
        qtext = item["query"]
        expected = [f.lower() for f in item["expected_files"]]
        cat = item.get("category", "general")

        ans, files, sources = execute_file_search(user, qtext, "local", max_results=5)
        retrieved_names = [f["name"].lower() for f in files]

        p1 = 1 if (retrieved_names and retrieved_names[0] in expected) else 0
        p5 = 1 if any(rn in expected for rn in retrieved_names[:5]) else 0

        hits_at_1 += p1
        hits_at_5 += p5

        p1_mark = "PASS" if p1 else "FAIL"
        p5_mark = "PASS" if p5 else "FAIL"

        print(f"{qid:<12} | {cat[:28]:<28} | {p1_mark:<5} | {p5_mark:<5} | {qtext[:45]}")
        results.append({
            "id": qid,
            "query": qtext,
            "expected": expected,
            "retrieved": retrieved_names,
            "p1": p1,
            "p5": p5,
        })

    precision_1 = hits_at_1 / total if total > 0 else 0.0
    precision_5 = hits_at_5 / total if total > 0 else 0.0

    print("\n" + "=" * 60)
    print("EVALUATION RESULTS SUMMARY")
    print("=" * 60)
    print(f"Total Evaluated Queries: {total}")
    print(f"Precision@1 (Top result is correct): {precision_1 * 100:.2f}% ({hits_at_1}/{total})")
    print(f"Precision@5 (Correct in top 5):     {precision_5 * 100:.2f}% ({hits_at_5}/{total})")
    print("=" * 60)

    return precision_1, precision_5


if __name__ == "__main__":
    q_file = Path("tests/eval_queries.json")
    evaluate_queries(q_file)
