#!/usr/bin/env python3
"""Export live ERP-to-Odoo account mappings to a UTF-8 CSV.

Connections come from dbconfig.erppeek and dbconfig.erppeek_odoo.
Set ODOO_API_KEY or enter the key at the prompt.
Each ERP account produces one row, including unmapped or missing Odoo accounts.
Example: python scripts/export_account_mapping_csv.py --output accounts.csv
"""

import argparse
import csv
import getpass
import os
from pathlib import Path
import sys
import xmlrpc.client


COMPANY_NAME = "Som Energia SCCL Compañía"
HEADER = ["compte erp", "nom erp", "compte odoo", "nom odoo"]


def connect_odoo(config, prompt_credentials=False):
    url = config["server"].rstrip("/")
    environment_key = os.environ.get("ODOO_API_KEY")
    if environment_key and not prompt_credentials:
        secret = environment_key
        credential_source = "ODOO_API_KEY environment variable"
    else:
        secret = getpass.getpass("Odoo API key/password: ")
        credential_source = "secure prompt"
    common = xmlrpc.client.ServerProxy(url + "/xmlrpc/2/common")
    uid = common.authenticate(config["db"], config["user"], secret, {})
    if not uid:
        raise RuntimeError(
            "Odoo authentication failed for {} on database {!r} as {!r}. "
            "Credential source: {}. Verify the key and compare with the "
            "working updater command."
            .format(url, config["db"], config["user"], credential_source)
        )
    models = xmlrpc.client.ServerProxy(url + "/xmlrpc/2/object")

    def call(model, method, positional, keyword):
        return models.execute_kw(
            config["db"], uid, secret, model, method, positional, keyword,
        )

    return call


def get_odoo_names(call, codes, company_name, language=None):
    companies = call(
        "res.company", "search_read", [[("name", "=", company_name)]],
        {"fields": ["name"], "limit": 2},
    )
    if len(companies) != 1:
        raise ValueError("Expected exactly one accessible company named {!r}".format(company_name))
    company_id = companies[0]["id"]
    context = {"allowed_company_ids": [company_id], "active_test": False}
    if language:
        context["lang"] = language
    fields = call("account.account", "fields_get", [], {"attributes": ["type"]})
    company_field = "company_ids" if "company_ids" in fields else "company_id"
    names = {}
    codes = sorted(codes)
    for start in range(0, len(codes), 200):
        accounts = call(
            "account.account", "search_read",
            [[("code", "in", codes[start:start + 200]),
              (company_field, "in", [company_id])]],
            {"fields": ["code", "name"], "context": context},
        )
        for account in accounts:
            code = account["code"]
            if code in names:
                raise ValueError(
                    "Multiple Odoo accounts match code {} in this company".format(code))
            names[code] = account["name"] or ""
    return names


def export_accounts(accounts, names, output):
    totals = dict(rows=0, unmapped=0, missing=0)
    with open(output, "w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(HEADER)
        for account in sorted(accounts, key=lambda item: (item["code"], item["id"])):
            code = account.get("odoo_account_code") or ""
            writer.writerow([account["code"], account["name"] or "", code, names.get(code, "")])
            totals["rows"] += 1
            if not code:
                totals["unmapped"] += 1
            elif code not in names:
                totals["missing"] += 1
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("account_mapping.csv"))
    parser.add_argument("--company", default=COMPANY_NAME, help="Odoo company name")
    parser.add_argument("--lang", help="Odoo language code; defaults to the user's language")
    parser.add_argument(
        "--prompt-credentials", action="store_true",
        help="Prompt for the Odoo key even when ODOO_API_KEY is set",
    )
    args = parser.parse_args()

    import dbconfig
    from erppeek import Client

    erp = Client(**dbconfig.erppeek)
    context = {"active_test": False}
    ids = erp.AccountAccount.search([], context=context)
    accounts = erp.AccountAccount.read(
        ids, ["code", "name", "odoo_account_code"], context=context,
    ) if ids else []
    codes = {account["odoo_account_code"]
             for account in accounts if account.get("odoo_account_code")}
    call = connect_odoo(dbconfig.erppeek_odoo, args.prompt_credentials)
    names = get_odoo_names(call, codes, args.company, args.lang)
    totals = export_accounts(accounts, names, args.output)
    print(
        "Exported {rows} rows; unmapped: {unmapped}; Odoo accounts \
                not found: {missing}".format(**totals))
    print("Output: {}".format(args.output.resolve()))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ImportError, OSError, ValueError, RuntimeError, xmlrpc.client.Error) as exc:
        print("ERROR: {}".format(exc))
        sys.exit(1)
