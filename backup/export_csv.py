from __future__ import annotations

import argparse
import csv

from study.database import export_rows, init_db


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="data/study.sqlite3")
    parser.add_argument("--output", default="data/sep_upp_user_study.csv")
    args = parser.parse_args()
    init_db(args.database)
    rows = export_rows(args.database)
    fieldnames = list(rows[0].keys()) if rows else ["participant_code"]
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(args.output)


if __name__ == "__main__":
    main()
