#!/usr/bin/env python3
"""Remove repeated account codes from a CSV, keeping the first name."""

import argparse
import csv
from pathlib import Path


def deduplicate(path):
    rows = []
    seen = set()
    removed = 0
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != ["code", "name"]:
            raise ValueError("CSV header must be code,name")
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Invalid CSV row at line {}".format(reader.line_num))
            code = row["code"].strip()
            if not code or not row["name"].strip():
                raise ValueError("Empty code or name at line {}".format(reader.line_num))
            if code in seen:
                removed += 1
                continue
            seen.add(code)
            rows.append(row)
    if removed:
        temporary = path.with_name(path.name + ".tmp")
        with temporary.open("x", newline="", encoding="utf-8") as destination:
            try:
                writer = csv.DictWriter(destination, fieldnames=["code", "name"])
                writer.writeheader()
                writer.writerows(rows)
            except Exception:
                temporary.unlink()
                raise
        temporary.replace(path)
    print("Kept {} accounts; removed {} duplicate rows".format(len(rows), removed))
    return rows, removed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input", nargs="?", type=Path,
        default=Path(__file__).with_name("comptes_comptables_nom_odoo.csv"),
    )
    deduplicate(parser.parse_args().input)
