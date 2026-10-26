#!/usr/bin/env python3
"""Compare a one-column account-code CSV with Odoo and optionally delete extras.

The CSV can contain codes with or without three-digit separators (for example
``100.000.000`` or ``100000000``). Blank rows and ``N/A`` values are ignored.
The default mode only reports differences. Deletion requires both ``--apply``
and ``--confirm-delete`` and is limited to accounts without journal items.

Example:
    python scripts/check_odoo_accounts.py --input /path/accounts.csv \\
        --url https://odoo.example.com --db production --username user@example.com
    python scripts/check_odoo_accounts.py --input /path/accounts.csv \\
        --url https://odoo.example.com --db production --username user@example.com \\
        --apply --confirm-delete
"""

import argparse
import csv
import getpass
import os
from pathlib import Path
import re
import sys
import xmlrpc.client


COMPANY_NAME = "Som Energia SCCL Compañía"
CODE_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)*$")


def normalize_code(value):
    """Remove separator dots from a numeric account code."""
    code = str(value or "").strip()
    if not code or not CODE_RE.fullmatch(code):
        return None
    return code.replace(".", "")


def read_account_codes(path):
    """Read a one-column CSV, returning normalized codes and duplicate count."""
    codes = set()
    duplicates = 0
    with open(path, newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.reader(csv_file)
        for row in reader:
            if not row or not any(value.strip() for value in row):
                continue
            if len(row) != 1:
                raise ValueError(
                    "Expected one account code per row at CSV line {}".format(
                        reader.line_num
                    )
                )
            raw_code = row[0].strip()
            if raw_code.upper() == "N/A":
                continue
            code = normalize_code(raw_code)
            if code is None:
                raise ValueError(
                    "Invalid account code at CSV line {}: {!r}".format(
                        reader.line_num, raw_code
                    )
                )
            if code in codes:
                duplicates += 1
            codes.add(code)
    if not codes:
        raise ValueError("CSV contains no valid account codes")
    return codes, duplicates


def find_company_and_field(call, company_name):
    companies = call(
        "res.company", "search_read", [[("name", "=", company_name)]],
        {"fields": ["name"], "limit": 2},
    )
    if len(companies) != 1:
        raise ValueError(
            "Expected exactly one accessible company named {!r}".format(company_name)
        )
    fields = call("account.account", "fields_get", [], {"attributes": ["type"]})
    if "company_ids" in fields:
        company_field = "company_ids"
    elif "company_id" in fields:
        company_field = "company_id"
    else:
        raise ValueError("Odoo account.account has no company field")
    return companies[0]["id"], company_field


def fetch_company_accounts(call, company_id, company_field):
    if company_field == "company_ids":
        domain = [(company_field, "in", [company_id])]
    else:
        domain = [(company_field, "=", company_id)]
    return call(
        "account.account", "search_read", [domain],
        {
            "fields": ["id", "code", "name", company_field],
            "context": {"allowed_company_ids": [company_id], "active_test": False},
        },
    )


def matching_codes(csv_codes, accounts):
    """Return CSV codes and their Odoo matches, plus ERP normalization counts."""
    accounts_by_code = {}
    invalid_accounts = []
    for account in accounts:
        normalized = normalize_code(account.get("code"))
        if normalized is None:
            invalid_accounts.append(account)
            continue
        accounts_by_code.setdefault(normalized, []).append(account)
    rows = []
    for code in sorted(csv_codes):
        matches = accounts_by_code.get(code, [])
        state = "EXISTS" if len(matches) == 1 else "AMBIGUOUS" if matches else "MISSING"
        rows.append((code, state, matches))
    return rows, accounts_by_code, invalid_accounts


def audit_accounts(call, csv_codes, company_id, company_field, apply=False):
    accounts = fetch_company_accounts(call, company_id, company_field)
    csv_rows, accounts_by_code, invalid_accounts = matching_codes(csv_codes, accounts)
    print("CSV codes present in Odoo:")
    for code, state, matches in csv_rows:
        print("  {} {}".format(state, code))
        if state == "AMBIGUOUS":
            for account in matches:
                print("    account ID {} ({})".format(account["id"], account.get("code")))

    extras = []
    for account in accounts:
        code = normalize_code(account.get("code"))
        if code is not None and code not in csv_codes:
            extras.append(account)
    print("\nOdoo accounts absent from CSV:")
    if not extras:
        print("  None")

    totals = {"deleted": 0, "would_delete": 0, "has_moves": 0, "skipped": 0}
    for account in extras:
        account_id = account["id"]
        raw_code = account.get("code") or "<empty>"
        normalized = normalize_code(account.get("code"))
        reason = None
        if len(accounts_by_code.get(normalized, [])) > 1:
            reason = "duplicate normalized Odoo code"
        elif (
            company_field == "company_ids"
            and set(account.get(company_field) or []) != {company_id}
        ):
            reason = "shared with another company"

        if reason:
            totals["skipped"] += 1
            print("  SKIPPED {} (ID {}): {}".format(raw_code, account_id, reason))
            continue

        move_line_ids = call(
            "account.move.line", "search",
            [[("account_id", "=", account_id)]],
            {"limit": 1, "context": {"allowed_company_ids": [company_id]}},
        )
        if move_line_ids:
            totals["has_moves"] += 1
            print("  PROTECTED {} (ID {}): has journal items".format(raw_code, account_id))
            continue

        if apply:
            result = call("account.account", "unlink", [[account_id]], {})
            if not result:
                raise RuntimeError("Odoo did not confirm deletion of account {}".format(raw_code))
            totals["deleted"] += 1
            print("  DELETED {} (ID {})".format(raw_code, account_id))
        else:
            totals["would_delete"] += 1
            print("  WOULD DELETE {} (ID {})".format(raw_code, account_id))

    if invalid_accounts:
        totals["skipped"] += len(invalid_accounts)
        print("\nSkipped {} Odoo accounts with non-numeric codes.".format(len(invalid_accounts)))
    present = sum(state == "EXISTS" for _, state, _ in csv_rows)
    missing = sum(state == "MISSING" for _, state, _ in csv_rows)
    ambiguous = sum(state == "AMBIGUOUS" for _, state, _ in csv_rows)
    print(
        "\nSummary: {} present, {} missing, {} ambiguous; "
        "{} {}, {} protected by journal items, {} skipped.".format(
            present, missing, ambiguous,
            totals["deleted"] if apply else totals["would_delete"],
            "deleted" if apply else "eligible for deletion",
            totals["has_moves"], totals["skipped"],
        )
    )
    return totals


def connect_odoo(url, database, username):
    secret = os.environ.get("ODOO_API_KEY") or getpass.getpass("Odoo API key/password: ")
    common = xmlrpc.client.ServerProxy(url.rstrip("/") + "/xmlrpc/2/common")
    uid = common.authenticate(database, username, secret, {})
    if not uid:
        raise RuntimeError("Odoo authentication failed")
    models = xmlrpc.client.ServerProxy(url.rstrip("/") + "/xmlrpc/2/object")

    def call(model, method, positional, keyword):
        return models.execute_kw(
            database, uid, secret, model, method, positional, keyword,
        )

    return call


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="One-column account-code CSV")
    parser.add_argument("--url", required=True, help="Odoo server URL")
    parser.add_argument("--db", required=True, help="Odoo database name")
    parser.add_argument("--username", required=True, help="Odoo user login")
    parser.add_argument("--company", default=COMPANY_NAME, help="Exact Odoo company name")
    parser.add_argument("--apply", action="store_true", help="Delete eligible extra accounts")
    parser.add_argument(
        "--confirm-delete", action="store_true",
        help="Required together with --apply to enable deletion",
    )
    args = parser.parse_args(arguments)
    if args.apply != args.confirm_delete:
        parser.error("--apply and --confirm-delete must be used together")

    csv_codes, duplicates = read_account_codes(args.input)
    print("Read {} unique CSV account codes ({} duplicate rows ignored).".format(
        len(csv_codes), duplicates,
    ))
    call = connect_odoo(args.url, args.db, args.username)
    company_id, company_field = find_company_and_field(call, args.company)
    print("Company: {} (ID {})".format(args.company, company_id))
    audit_accounts(call, csv_codes, company_id, company_field, apply=args.apply)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, xmlrpc.client.Error) as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)  # noqa: E999
        sys.exit(1)
