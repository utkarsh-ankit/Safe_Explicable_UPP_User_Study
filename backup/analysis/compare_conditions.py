from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from statistics import mean


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    args = parser.parse_args()
    grouped = defaultdict(list)
    with open(args.csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not row.get("scores_json"):
                continue
            scores = json.loads(row["scores_json"])
            key = (row["domain_name"], row["assigned_condition"])
            grouped[key].append(scores)

    for (domain, condition), rows in sorted(grouped.items()):
        print(f"{domain} | {condition} | n={len(rows)}")
        for metric in [
            "full_user_reward",
            "partial_user_reward",
            "task_reward",
            "true_safety_cost",
            "steps",
        ]:
            print(f"  {metric}: {mean(float(r[metric]) for r in rows):.3f}")
        print(f"  completion rate: {mean(1.0 if r['completed'] else 0.0 for r in rows):.3f}")
        print(f"  hidden hazard rate: {mean(1.0 if r['hidden_hazard_entered'] else 0.0 for r in rows):.3f}")


if __name__ == "__main__":
    main()
