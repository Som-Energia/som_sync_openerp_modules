# -*- coding: utf-8 -*-
"""
Script per exportar saldos de comptes comptables des d'un període especial.

   python scripts/export_account_special_period_balances_csv.py \
     --account-prefix 572 \
     --date 2025-12-31 \
     --output /tmp/saldos_572_2025-12-31.csv
"""
from __future__ import print_function, unicode_literals

import io
import sys

try:
    import argparse
except ImportError:
    argparse = None

import dbconfig
from erppeek import Client
from tqdm import tqdm


def to_text(value):
    if value is None:
        return u""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return u"%s" % value


def format_amount(value):
    if value in (None, False, u"", ""):
        return u""
    return u"{0:.2f}".format(float(value))


def get_accounts(client, account_code=None, account_prefix=None, account_pattern=None):
    domain = []
    if account_code:
        domain = [("code", "=", account_code)]
    elif account_prefix:
        domain = [("code", "like", "%s%%" % account_prefix)]
    else:
        domain = [("code", "like", account_pattern)]

    account_ids = client.AccountAccount.search(domain, order="code asc, id asc")
    if not account_ids:
        raise RuntimeError("No s'ha trobat cap compte pels filtres indicats")

    return client.AccountAccount.read(account_ids, ["id", "code", "name"])


def get_special_periods_for_date(client, target_date):
    period_ids = client.AccountPeriod.search([
        ("special", "=", True),
        ("date_stop", "=", target_date),
    ], order="code asc, id asc")

    if not period_ids:
        period_ids = client.AccountPeriod.search([
            ("special", "=", True),
            ("date_start", "=", target_date),
        ], order="code asc, id asc")

    if not period_ids:
        return []

    return client.AccountPeriod.read(period_ids, ["id", "code", "name", "date_start", "date_stop"])


def build_period_map(periods):
    period_map = {}
    for period in periods:
        period_map[int(period["id"])] = period
    return period_map


def get_balance_rows_for_account(client, account_id, period_ids):
    if not period_ids:
        return []

    line_ids = client.AccountMoveLine.search([
        ("account_id", "=", account_id),
        ("period_id", "in", period_ids),
    ], order="date asc, id asc")

    if not line_ids:
        return []

    return client.AccountMoveLine.read(line_ids, ["debit", "credit", "period_id"])


def compute_balance(lines):
    balance = 0.0
    for line in lines:
        debit = float(line.get("debit") or 0.0)
        credit = float(line.get("credit") or 0.0)
        balance += debit - credit
    return balance


def get_used_period_codes(lines, period_map):
    codes = []
    used_ids = set()

    for line in lines:
        period_value = line.get("period_id")
        if not isinstance(period_value, (list, tuple)) or not period_value:
            continue
        period_id = int(period_value[0])
        if period_id in used_ids:
            continue
        used_ids.add(period_id)
        period = period_map.get(period_id, {})
        code = to_text(period.get("code") or period.get("name") or period_id)
        codes.append(code)

    return u",".join(codes)


def export_csv(account_code, account_prefix, account_pattern, target_date, output_path):
    client = Client(**dbconfig.erppeek)

    accounts = get_accounts(
        client,
        account_code=account_code,
        account_prefix=account_prefix,
        account_pattern=account_pattern,
    )
    periods = get_special_periods_for_date(client, target_date)
    period_ids = [int(period["id"]) for period in periods]
    period_codes = u",".join([to_text(period.get("code") or period.get("name"))
                             for period in periods])
    period_map = build_period_map(periods)

    with io.open(output_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(
            u"account_code;account_name;date;special_period_found;special_period_codes;line_found;line_count;line_period_codes;balance\n"  # noqa: E501
        )
        for account in tqdm(accounts, total=len(accounts), desc="Exportant saldos"):
            lines = get_balance_rows_for_account(client, account["id"], period_ids)
            line_found = bool(lines)
            balance = compute_balance(lines) if line_found else False
            used_period_codes = get_used_period_codes(lines, period_map) if line_found else u""

            row = u"%s;%s;%s;%s;%s;%s;%s;%s;%s\n" % (
                to_text(account.get("code")),
                to_text(account.get("name")).replace(u";", u","),
                to_text(target_date),
                to_text(bool(period_ids)),
                period_codes.replace(u";", u","),
                to_text(line_found),
                to_text(len(lines)),
                used_period_codes.replace(u";", u","),
                format_amount(balance),
            )
            fh.write(row)

    print("CSV generat: %s (%s comptes)" % (output_path, len(accounts)))
    if not period_ids:
        print("AVIS: no s'ha trobat cap període especial per a la data %s" % target_date)


def parse_args(argv):
    if argparse is None:
        raise RuntimeError("argparse no disponible")

    parser = argparse.ArgumentParser(
        description="Exporta saldos de comptes comptables des d'un període especial"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--account", help="Codi compte comptable exacte (ex: 572000000005)")
    group.add_argument("--account-prefix", help="Prefix de compte comptable (ex: 572)")
    group.add_argument("--account-pattern", help="Patró like d'OpenERP (ex: 572%)")
    parser.add_argument("--date", required=True, help="Data del període especial (YYYY-MM-DD)")
    parser.add_argument("--output", required=True, help="Ruta fitxer CSV de sortida")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    export_csv(
        args.account,
        args.account_prefix,
        args.account_pattern,
        args.date,
        args.output,
    )


if __name__ == "__main__":
    main()
