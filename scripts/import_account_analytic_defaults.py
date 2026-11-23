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
import io
import os
import sys


DEFAULT_INPUT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "account_analytic_mapping.csv",
)
ACCOUNT_HEADER = "compte_comptabel"
ANALYTIC_HEADER = "compte_analitic"

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


def _index_records(records, field):
    indexed = {}
    for record in records:
        key = _text(record.get(field))
        if key:
            indexed.setdefault(key, []).append(record["id"])
    return indexed


def _get_records(client, model, field):
    model_proxy = getattr(client, model)
    ids = model_proxy.search([])
    return model_proxy.read(ids, ["id", field]) if ids else []


def resolve_mappings(client, mappings):
    accounts = _index_records(
        _get_records(client, "AccountAccount", "code"), "code"
    )
    analytics = _index_records(
        _get_records(client, "AccountAnalyticAccount", "name"),
        "name",
    )

    defaults = []
    for account_code, analytic_name in mappings:
        account_code = _text(account_code)
        analytic_name = _text(analytic_name)
        account_ids = accounts.get(account_code, [])
        if len(account_ids) != 1:
            reason = "not found" if not account_ids else "ambiguous"
            raise ValueError(
                "OpenERP account code {} {}".format(account_code, reason)
            )
        analytic_ids = analytics.get(analytic_name, [])
        if len(analytic_ids) != 1:
            reason = "not found" if not analytic_ids else "ambiguous"
            raise ValueError(
                "Analytic account {} {}".format(analytic_name, reason)
            )
        defaults.append({
            "account_id": account_ids[0],
            "analytic_id": analytic_ids[0],
            "sequence": 100,
        })
    return defaults


def create_defaults(client, defaults):
    model = client.AccountAnalyticDefault
    for values in defaults:
        model.create(values)
    return len(defaults)


def parse_arguments(arguments):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", default=DEFAULT_INPUT, help="Mapping CSV file"
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Create analytic defaults in OpenERP; omitted means validation only."
    )
    return parser.parse_args(arguments)


def main(arguments=None):
    args = parse_arguments(arguments)
    mappings = read_mappings(args.input)
    try:
        from erppeek import Client
        import dbconfig
    except ImportError:
        raise RuntimeError("erppeek and scripts/dbconfig.py are required")

    client = Client(**dbconfig.erppeek)
    defaults = resolve_mappings(client, mappings)
    print("Validated {} analytic default mappings".format(len(defaults)))
    if not args.apply:
        print("Dry run only; use --apply to create these records.")
        return 0

    created = create_defaults(client, defaults)
    print("Created {} analytic defaults".format(created))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print("ERROR: {}".format(error), file=sys.stderr)
        sys.exit(1)
