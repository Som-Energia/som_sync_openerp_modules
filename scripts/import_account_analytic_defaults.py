# -*- coding: utf-8 -*-
"""Create OpenERP analytic defaults from an account mapping CSV.

The UTF-8 input file is semicolon separated and contains
``compte_comptabel;compte_analitic`` columns.

Examples:
    python scripts/import_account_analytic_defaults.py
    python scripts/import_account_analytic_defaults.py --apply
    python scripts/import_account_analytic_defaults.py --input /tmp/mapping.csv --apply
"""
from __future__ import print_function, unicode_literals

import argparse
import csv
import io
import os
import sys


DEFAULT_INPUT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "account_analytic_mapping.csv",
)
ACCOUNT_HEADER = "compte_comptabel"
ANALYTIC_HEADER = "compte_analitic"
DEFAULT_CONDITION_FIELDS = (
    "product_id",
    "partner_id",
    "user_id",
    "company_id",
    "date_start",
    "date_stop",
)
REPORT_FIELDS = (
    "account_code_csv",
    "account_code_erp",
    "analytic_mapping_csv",
    "analytic_code",
    "account_id",
    "analytic_id",
    "status",
    "detail",
)

try:
    text_type = unicode
except NameError:
    text_type = str


def read_mappings(path):
    mappings = []
    with io.open(path, "r", encoding="utf-8") as mapping_file:
        for line_number, line in enumerate(mapping_file, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            columns = [value.strip() for value in line.split(";")]
            if line_number == 1 and columns == [ACCOUNT_HEADER, ANALYTIC_HEADER]:
                continue
            if len(columns) != 2:
                raise ValueError(
                    "Line {} must contain {};{}".format(
                        line_number, ACCOUNT_HEADER, ANALYTIC_HEADER
                    )
                )
            account_code, analytic_name = columns
            if not account_code or not analytic_name:
                continue
            mappings.append((account_code, analytic_name))
    if not mappings:
        raise ValueError("The mapping file contains no complete mappings")
    return mappings


def _text(value):
    if isinstance(value, bytes) and not isinstance(value, text_type):
        return value.decode("utf-8")
    return value


def _account_code(value):
    return _text(value).replace(".", "")


def _analytic_code(value):
    return _text(value)[:6]


def _index_records(records, field, normalize=None):
    indexed = {}
    for record in records:
        key = record.get(field)
        if normalize:
            key = normalize(key)
        else:
            key = _text(key)
        if key:
            indexed.setdefault(key, []).append(record["id"])
    return indexed


def _get_records(client, model, field):
    model_proxy = getattr(client, model)
    ids = model_proxy.search([])
    return model_proxy.read(ids, ["id", field]) if ids else []


def _many2one_id(value):
    if isinstance(value, (list, tuple)):
        return value[0] if value else False
    return value or False


def _existing_default_pairs(client):
    model = client.AccountAnalyticDefault
    ids = model.search([])
    if not ids:
        return set()
    fields = ["account_id", "analytic_id"] + list(DEFAULT_CONDITION_FIELDS)
    records = model.read(ids, fields)
    pairs = set()
    for record in records:
        if any(record.get(field) for field in DEFAULT_CONDITION_FIELDS):
            continue
        account_id = _many2one_id(record.get("account_id"))
        analytic_id = _many2one_id(record.get("analytic_id"))
        if account_id and analytic_id:
            pairs.add((account_id, analytic_id))
    return pairs


def resolve_mappings(client, mappings):
    accounts = _index_records(
        _get_records(client, "AccountAccount", "code"),
        "code",
        normalize=_account_code,
    )
    analytics = _index_records(
        _get_records(client, "AccountAnalyticAccount", "code"),
        "code",
    )
    existing_pairs = _existing_default_pairs(client)
    seen_pairs = set()
    rows = []
    for account_code_csv, analytic_mapping_csv in mappings:
        account_code = _account_code(account_code_csv)
        analytic_code = _analytic_code(analytic_mapping_csv)
        account_ids = accounts.get(account_code, [])
        analytic_ids = analytics.get(analytic_code, [])
        details = []
        if len(account_ids) != 1:
            status = "account_not_found" if not account_ids else "account_ambiguous"
            details.append("{}: {}".format(status, account_code))
        if len(analytic_ids) != 1:
            status = "analytic_not_found" if not analytic_ids else "analytic_ambiguous"
            details.append("{}: {}".format(status, analytic_code))

        account_id = account_ids[0] if len(account_ids) == 1 else ""
        analytic_id = analytic_ids[0] if len(analytic_ids) == 1 else ""
        row = {
            "account_code_csv": account_code_csv,
            "account_code_erp": account_code,
            "analytic_mapping_csv": analytic_mapping_csv,
            "analytic_code": analytic_code,
            "account_id": account_id,
            "analytic_id": analytic_id,
            "status": "skipped" if details else "ready",
            "detail": "; ".join(details),
        }
        if not details:
            pair = (account_id, analytic_id)
            if pair in existing_pairs:
                row["status"] = "already_exists"
                row["detail"] = "Matching unconditional default already exists"
            elif pair in seen_pairs:
                row["status"] = "duplicate_mapping"
                row["detail"] = "Same account and analytic mapping appeared earlier"
            else:
                seen_pairs.add(pair)
        rows.append(row)
    return rows


def create_defaults(client, rows):
    model = client.AccountAnalyticDefault
    created = 0
    for row in rows:
        if row["status"] != "ready":
            continue
        values = {
            "account_id": row["account_id"],
            "analytic_id": row["analytic_id"],
            "sequence": 100,
        }
        try:
            model.create(values)
        except Exception as error:
            row["status"] = "error"
            row["detail"] = _text(str(error))
        else:
            row["status"] = "created"
            created += 1
    return created


def write_report(path, rows):
    if sys.version_info[0] == 2:
        report_file = open(path, "wb")
    else:
        report_file = io.open(path, "w", encoding="utf-8", newline="")
    try:
        writer = csv.writer(report_file, delimiter=str(";"))
        writer.writerow([_report_value(field) for field in REPORT_FIELDS])
        for row in rows:
            writer.writerow([
                _report_value(row.get(field, "")) for field in REPORT_FIELDS
            ])
    finally:
        report_file.close()


def _report_value(value):
    if sys.version_info[0] == 2 and isinstance(value, text_type):
        return value.encode("utf-8")
    return value


def summarize(rows):
    counts = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return counts


def parse_arguments(arguments):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", default=DEFAULT_INPUT, help="Mapping CSV file"
    )
    parser.add_argument(
        "--report",
        help="CSV report path; defaults to <input>_import_report.csv",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Create analytic defaults in OpenERP; omitted means validation only."
    )
    return parser.parse_args(arguments)


def main(arguments=None):
    args = parse_arguments(arguments)
    mappings = read_mappings(args.input)
    report_path = args.report or os.path.splitext(args.input)[0] + "_import_report.csv"
    try:
        from erppeek import Client
        import dbconfig
    except ImportError:
        raise RuntimeError("erppeek and scripts/dbconfig.py are required")

    client = Client(**dbconfig.erppeek)
    rows = resolve_mappings(client, mappings)
    if args.apply:
        created = create_defaults(client, rows)
    else:
        created = 0
        for row in rows:
            if row["status"] == "ready":
                row["status"] = "would_create"
    write_report(report_path, rows)

    counts = summarize(rows)
    print("Mappings: {}".format(len(rows)))
    print("Created: {}".format(created))
    for status in sorted(counts):
        print("{}: {}".format(status, counts[status]))
    print("CSV report: {}".format(os.path.abspath(report_path)))
    return 1 if counts.get("error") else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print("ERROR: {}".format(error), file=sys.stderr)
        sys.exit(1)
