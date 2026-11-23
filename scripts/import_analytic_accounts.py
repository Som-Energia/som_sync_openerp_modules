#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Import Odoo analytic accounts into OpenERP as static mappings.

The default mode validates the CSV, resolves each Odoo identity and reports the
local changes without writing. Use --apply to create missing local accounts and
their static odoo.sync mappings.

Import accounts and static mappings for the only_moves destination:
    python scripts/import_analytic_accounts.py --input \\
        som_sync_openerp/migrations/comptes_analitics.csv \\
        --erp-company-id 1 --odoo-company-id 2 --odoo-plan-id 3
    python scripts/import_analytic_accounts.py --input \\
        som_sync_openerp/migrations/comptes_analitics.csv \\
        --erp-company-id 1 --odoo-company-id 2 --odoo-plan-id 3 --apply

The Odoo company and plan IDs are specific to the configured Odoo instance.
The catalog lookup uses the dedicated ``odoo_api_key_only_moves`` key.
Static mappings are created exclusively under the ``only_moves`` profile.
Set scripts/dbconfig.py to the intended OpenERP database before running this
script; that file currently defaults to production.
"""

from __future__ import print_function, unicode_literals

import argparse
import csv
import io
import os
import sys


ANALYTIC_ACCOUNT = "account.analytic.account"
SYNC = "odoo.sync"
SYNC_PROFILE = "only_moves"
ROOT_NAME = u"Projectes Odoo"
ROOT_CODE = "ODOO-PROJECTS"
CONTEXT = {"active_test": False}
CSV_HEADERS = [
    u"Compte analític",
    u"Referència",
    u"Client/a",
    u"Pla",
    u"Empresa",
    u"Deure",
    u"Haver",
    u"Saldo",
]
ANALYTIC_FIELDS = [
    "id", "name", "code", "company_id", "parent_id", "type", "state", "active",
]
SYNC_FIELDS = ["odoo_id", "sync_state", "sync_profile"]
PY2 = sys.version_info[0] == 2

try:
    integer_types = (int, long)
    text_type = unicode
except NameError:
    integer_types = (int,)
    text_type = str


def text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return text_type(value)


def positive_int(value):
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("must be a positive integer")
    if result <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return result


def read_accounts(path):
    """Parse and validate the Odoo export without dropping leading zeroes."""
    source = open(path, "rb") if PY2 else io.open(
        path, "r", encoding="utf-8-sig", newline="")
    accounts = []
    references = set()
    with source:
        reader = csv.DictReader(source, delimiter=str(";"))
        headers = [text(header).lstrip(u"\ufeff") for header in (reader.fieldnames or [])]
        if headers != CSV_HEADERS:
            raise ValueError(
                "CSV header must be: {}".format(";".join(CSV_HEADERS)))
        if PY2:
            reader.fieldnames = [header.encode("utf-8") for header in CSV_HEADERS]
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(
                    "Invalid CSV row at line {}".format(reader.line_num))
            values = {
                header: text(row[key]).strip()
                for header, key in zip(CSV_HEADERS, reader.fieldnames)
            }
            account = {
                "name": values[u"Compte analític"],
                "reference": values[u"Referència"],
                "plan": values[u"Pla"],
                "company": values[u"Empresa"],
            }
            if not all(account.values()):
                raise ValueError(
                    "Name, reference, plan and company are required at CSV line {}"
                    .format(reader.line_num))
            if len(account["name"]) > 64 or len(account["reference"]) > 24:
                raise ValueError(
                    "Name or reference exceeds the OpenERP field length at CSV line {}"
                    .format(reader.line_num))
            if account["reference"] in references:
                raise ValueError(
                    "Duplicate analytic reference at CSV line {}: {}".format(
                        reader.line_num, account["reference"]))
            references.add(account["reference"])
            accounts.append(account)

    if not accounts:
        raise ValueError("CSV contains no analytic accounts")
    plans = set(account["plan"] for account in accounts)
    companies = set(account["company"] for account in accounts)
    if len(plans) != 1 or len(companies) != 1:
        raise ValueError("CSV must contain exactly one plan and one company")
    return accounts


def read_records(client, model, domain, fields):
    ids = client.execute(
        model, "search", domain, context=dict(CONTEXT))
    if not ids:
        return []
    return client.execute(
        model, "read", ids, fields, context=dict(CONTEXT))


def relation_id(value):
    return value[0] if isinstance(value, (list, tuple)) and value else False


def find_root(client, erp_company_id):
    roots = read_records(
        client,
        ANALYTIC_ACCOUNT,
        [("company_id", "=", erp_company_id), ("parent_id", "=", False)],
        ANALYTIC_FIELDS,
    )
    matches = [
        account for account in roots
        if account.get("code") == ROOT_CODE or account.get("name") == ROOT_NAME
    ]
    if len(matches) > 1:
        raise ValueError("Multiple root accounts match {!r}".format(ROOT_NAME))
    if not matches:
        return False

    root = matches[0]
    if (root.get("name") != ROOT_NAME or root.get("code") not in (False, ROOT_CODE)
            or root.get("type") != "view"
            or relation_id(root.get("company_id")) != erp_company_id
            or root.get("parent_id")
            or root.get("state") != "open"
            or root.get("active") is False):
        raise ValueError(
            "Existing root account {!r} does not match the expected view account"
            .format(ROOT_NAME))
    return root


def find_local_account(client, reference, erp_company_id, root_id):
    accounts = read_records(
        client,
        ANALYTIC_ACCOUNT,
        [("code", "=", reference), ("company_id", "=", erp_company_id)],
        ANALYTIC_FIELDS,
    )
    if len(accounts) > 1:
        raise ValueError(
            "Multiple local analytic accounts use reference {}".format(reference))
    if not accounts:
        return False

    account = accounts[0]
    if not root_id:
        raise ValueError(
            "Local account {} exists but the {!r} parent does not".format(
                reference, ROOT_NAME))
    if (account.get("type") != "normal"
            or account.get("name") == ""
            or relation_id(account.get("company_id")) != erp_company_id
            or relation_id(account.get("parent_id")) != root_id
            or account.get("active") is False
            or account.get("state") != "open"):
        raise ValueError(
            "Existing account {} is not an active account under {!r}".format(
                reference, ROOT_NAME))
    return account


def find_mapping(client, account_id, expected_odoo_id=None):
    mappings = read_records(
        client,
        SYNC,
        [
            ("model.model", "=", ANALYTIC_ACCOUNT),
            ("res_id", "=", account_id),
            ("sync_profile", "=", SYNC_PROFILE),
        ],
        SYNC_FIELDS,
    )
    if len(mappings) > 1:
        raise ValueError(
            "Multiple odoo.sync mappings exist for local account {}".format(
                account_id))
    if not mappings:
        return False

    mapping = mappings[0]
    if expected_odoo_id and mapping.get("odoo_id") != expected_odoo_id:
        raise ValueError(
            "Local account {} is already mapped to a different Odoo ID".format(
                account_id))
    if mapping.get("sync_profile") != SYNC_PROFILE:
        raise ValueError(
            "Local account {} has a mapping under an unexpected profile".format(
                account_id))
    return mapping


def prepare_import(client, accounts, erp_company_id, odoo_company_id, odoo_plan_id):
    """Resolve every remote identity and validate all local conflicts first."""
    companies = client.execute(
        "res.company", "read", [erp_company_id], ["name"], context=dict(CONTEXT))
    if len(companies) != 1:
        raise ValueError("OpenERP company {} does not exist".format(erp_company_id))

    root = find_root(client, erp_company_id)
    root_id = root and root["id"] or False
    prepared = []
    for account in accounts:
        local_account = find_local_account(
            client, account["reference"], erp_company_id, root_id)
        odoo_id = client.execute(
            SYNC,
            "get_analytic_account_odoo_id",
            account["reference"],
            odoo_company_id,
            odoo_plan_id,
            account["company"],
            account["plan"],
            context=dict(CONTEXT, sync_profile=SYNC_PROFILE),
        )
        if isinstance(odoo_id, bool) or not isinstance(odoo_id, integer_types) or odoo_id <= 0:
            raise ValueError(
                "Invalid Odoo ID returned for analytic account {}".format(
                    account["reference"]))

        mapping = False
        if local_account:
            mapping = find_mapping(client, local_account["id"], odoo_id)
            if local_account.get("name") != account["name"]:
                raise ValueError(
                    "Local account {} has a different name; refusing an automatic rename"
                    .format(account["reference"]))
        prepared.append({
            "source": account,
            "local_account": local_account,
            "mapping": mapping,
            "odoo_id": odoo_id,
        })
    return {
        "company": companies[0],
        "root": root,
        "accounts": prepared,
    }


def apply_import(client, plan, erp_company_id):
    """Create only missing local records and preserve existing identities."""
    root = plan["root"]
    if not root:
        root_id = client.execute(
            ANALYTIC_ACCOUNT,
            "create",
            {
                "name": ROOT_NAME,
                "code": ROOT_CODE,
                "company_id": erp_company_id,
                "type": "view",
                "state": "open",
                "active": True,
            },
            context=dict(CONTEXT),
        )
        print("Created OpenERP parent account {} ({})".format(ROOT_NAME, root_id))
    else:
        root_id = root["id"]

    created_accounts = 0
    reused_accounts = 0
    created_mappings = 0
    for item in plan["accounts"]:
        account = item["source"]
        local_account = item["local_account"]
        if not local_account:
            local_id = client.execute(
                ANALYTIC_ACCOUNT,
                "create",
                {
                    "name": account["name"],
                    "code": account["reference"],
                    "company_id": erp_company_id,
                    "parent_id": root_id,
                    "type": "normal",
                    "state": "open",
                    "active": True,
                },
                context=dict(CONTEXT),
            )
            created_accounts += 1
        else:
            local_id = local_account["id"]
            reused_accounts += 1

        mapping = item["mapping"]
        if not mapping or mapping.get("sync_state") != "static":
            client.execute(
                SYNC,
                "syncronize_sync",
                ANALYTIC_ACCOUNT,
                "sync",
                local_id,
                context={
                    "is_static": True,
                    "odoo_id": item["odoo_id"],
                    "sync_profile": SYNC_PROFILE,
                },
            )
            if not mapping:
                created_mappings += 1

    return {
        "created_accounts": created_accounts,
        "reused_accounts": reused_accounts,
        "created_mappings": created_mappings,
    }


def parse_arguments(arguments):
    default_csv = os.path.join(
        os.path.dirname(__file__),
        "..",
        "som_sync_openerp",
        "migrations",
        "comptes_analitics.csv",
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=default_csv, help="Odoo analytic account CSV")
    parser.add_argument(
        "--erp-company-id", required=True, type=positive_int,
        help="Company ID in the configured OpenERP database")
    parser.add_argument(
        "--odoo-company-id", required=True, type=positive_int,
        help="Company ID in the configured Odoo instance")
    parser.add_argument(
        "--odoo-plan-id", required=True, type=positive_int,
        help="Analytic plan ID in the configured Odoo instance")
    parser.add_argument(
        "--apply", action="store_true",
        help="Create missing local accounts and static mappings; default is dry-run")
    return parser.parse_args(arguments)


def main(arguments=None):
    args = parse_arguments(arguments)
    accounts = read_accounts(args.input)
    try:
        import dbconfig
        from erppeek import Client
    except ImportError as error:
        raise RuntimeError(
            "dbconfig and erppeek are required to import analytic accounts: {}"
            .format(error))

    client = Client(**dbconfig.erppeek)
    plan = prepare_import(
        client,
        accounts,
        args.erp_company_id,
        args.odoo_company_id,
        args.odoo_plan_id,
    )
    create_count = sum(
        1 for item in plan["accounts"] if not item["local_account"])
    mapping_count = sum(
        1 for item in plan["accounts"]
        if not item["mapping"] or item["mapping"].get("sync_state") != "static")
    print(
        "Validated {} accounts for OpenERP company {} and Odoo company/plan {}/{}."
        .format(len(accounts), args.erp_company_id, args.odoo_company_id, args.odoo_plan_id))
    print(
        "Would create {} local accounts and {} static mappings under {!r}."
        .format(create_count, mapping_count, ROOT_NAME))
    if not args.apply:
        print("Dry-run only; no OpenERP records were changed.")
        return 0

    summary = apply_import(client, plan, args.erp_company_id)
    print(
        "Import complete: {} created, {} reused, {} mappings created."
        .format(
            summary["created_accounts"],
            summary["reused_accounts"],
            summary["created_mappings"],
        ))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print("ERROR: {}".format(error), file=sys.stderr)
        sys.exit(1)
