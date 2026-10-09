#!/usr/bin/env python3
"""Update existing Odoo 18 account names from a UTF-8 code,name CSV.

Uses Python's standard library and Odoo's XML-RPC API. Set ODOO_API_KEY
or enter an API key/password at the prompt. Missing accounts are skipped.
The same CSV name is applied in every active Odoo language.
Use --dry-run to preview changes without writing to Odoo.
"""

import argparse
import csv
import getpass
import os
from pathlib import Path
import sys
import xmlrpc.client


COMPANY_NAME = "Som Energia SCCL Compañía"
DEFAULT_INPUT = Path(__file__).with_name("comptes_comptables_nom_odoo.csv")


def read_accounts(path):
    accounts = {}
    with open(path, newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames != ["code", "name"]:
            raise ValueError("CSV header must be code,name")
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Invalid CSV row at line {}".format(reader.line_num))
            code, name = row["code"].strip(), row["name"].strip()
            if not code or not name:
                raise ValueError("Empty code or name at line {}".format(reader.line_num))
            if code in accounts and accounts[code] != name:
                raise ValueError("Conflicting names for code {}".format(code))
            accounts[code] = name
    if not accounts:
        raise ValueError("CSV contains no accounts")
    return accounts


def update_accounts(call, accounts, dry_run=False):
    companies = call(
        "res.company", "search_read", [[("name", "=", COMPANY_NAME)]],
        {"fields": ["name"], "limit": 2},
    )
    if len(companies) != 1:
        raise ValueError("Expected exactly one accessible company named {!r}".format(COMPANY_NAME))
    company_id = companies[0]["id"]
    context = {"allowed_company_ids": [company_id], "active_test": False}
    languages = call(
        "res.lang", "search_read", [[("active", "=", True)]],
        {"fields": ["code"], "order": "code"},
    )
    if not languages:
        raise ValueError("No active Odoo languages found")
    language_codes = [language["code"] for language in languages]
    context["lang"] = language_codes[0]

    # Odoo versions/customizations can expose either company relationship.
    fields = call("account.account", "fields_get", [], {"attributes": ["type"]})
    company_field = "company_ids" if "company_ids" in fields else "company_id"
    totals = dict(updated=0, unchanged=0, missing=0, skipped=0)
    print("Company: {} (ID {})".format(COMPANY_NAME, company_id))
    print("Languages: {}".format(", ".join(language_codes)))
    for code, name in accounts.items():
        matches = call(
            "account.account", "search_read",
            [[("code", "=", code), (company_field, "in", [company_id])]],
            {"fields": ["name", company_field], "context": context, "limit": 2},
        )
        if not matches:
            totals["missing"] += 1
            print("NOT FOUND {}".format(code))
            continue
        if len(matches) > 1:
            totals["skipped"] += 1
            print("SKIPPED {}: multiple matching accounts".format(code))
            continue
        account = matches[0]
        if company_field == "company_ids" and set(account[company_field]) != {company_id}:
            totals["skipped"] += 1
            print("SKIPPED {}: account shared with other companies".format(code))
            continue
        # Read every translation before writing: changing the source name can
        # change the fallback returned for languages without a stored value.
        changes = []
        for language in language_codes:
            language_context = dict(context, lang=language)
            translated = call(
                "account.account", "read", [[account["id"]]],
                {"fields": ["name"], "context": language_context},
            )[0]
            if translated["name"] != name:
                changes.append((language, translated["name"], language_context))
        if not changes:
            totals["unchanged"] += 1
            continue
        for language, old_name, language_context in changes:
            if not dry_run:
                result = call(
                    "account.account", "write", [[account["id"]], {"name": name}],
                    {"context": language_context},
                )
                if not result:
                    raise RuntimeError(
                        "Odoo did not confirm the update for {} ({})".format(code, language))
            print("{} {} [{}]: {!r} -> {!r}".format(
                "WOULD UPDATE" if dry_run else "UPDATED", code, language, old_name, name,
            ))
        totals["updated"] += 1
    print("{}: {}, unchanged: {}, not found: {}, skipped: {}".format(
        "Would update" if dry_run else "Updated", totals["updated"],
        totals["unchanged"], totals["missing"], totals["skipped"],
    ))
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Odoo server URL")
    parser.add_argument("--db", required=True, help="Odoo database name")
    parser.add_argument("--username", required=True, help="Odoo user login")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Input CSV file")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()
    accounts = read_accounts(args.input)
    secret = os.environ.get("ODOO_API_KEY") or getpass.getpass("Odoo API key/password: ")
    url = args.url.rstrip("/")
    common = xmlrpc.client.ServerProxy(url + "/xmlrpc/2/common")
    uid = common.authenticate(args.db, args.username, secret, {})
    if not uid:
        raise RuntimeError("Odoo authentication failed")
    models = xmlrpc.client.ServerProxy(url + "/xmlrpc/2/object")

    def call(model, method, positional, keyword):
        return models.execute_kw(args.db, uid, secret, model, method, positional, keyword)

    totals = update_accounts(call, accounts, args.dry_run)
    return 1 if totals["skipped"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, xmlrpc.client.Error) as exc:
        print("ERROR: {}".format(exc))
        sys.exit(1)
