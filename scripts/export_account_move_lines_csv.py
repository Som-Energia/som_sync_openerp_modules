# -*- coding: utf-8 -*-
"""
Script per exportar assentaments de bancs a un excel

   python scripts/export_account_move_lines_csv.py \
     --account 572000000005 \
     --date-from 2026-01-01 \
     --date-to 2026-01-31 \
     --output /tmp/moviments_572_gener_2026.csv
"""
from __future__ import print_function, unicode_literals

import io
import re
import sys

try:
    import argparse
except ImportError:
    argparse = None

import dbconfig
from erppeek import Client


def to_text(value):
    if value is None:
        return u""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return u"%s" % value


def classify_description(line_name, line_ref):
    name = to_text(line_name).strip()
    ref = to_text(line_ref).strip()
    lower_name = name.lower()

    remesa_match = re.search(r"\bremesa\s+(.+)$", name, re.IGNORECASE)
    if remesa_match:
        return u"[REMESA] %s" % remesa_match.group(1).strip()

    if u"comissió" in lower_name or u"comissio" in lower_name or u"comisión" in lower_name:
        return u"[COMISSIÓ] Comissió"

    if u"devoluc" in lower_name:
        return u"[DEVOLUCIONS] Devolucions"

    if ref and re.search(r"\d", ref):
        return u"[FACTURA] %s" % ref

    return name or ref


def amount_signed(debit, credit):
    debit = float(debit or 0.0)
    credit = float(credit or 0.0)
    return debit - credit


def format_amount(value):
    return (u"%.2f" % value)


def export_csv(account_code, date_from, date_to, output_path):
    client = Client(**dbconfig.erppeek)

    account_ids = client.AccountAccount.search([("code", "=", account_code)])
    if not account_ids:
        raise RuntimeError("No s'ha trobat el compte comptable: %s" % account_code)

    domain = [
        ("account_id", "in", account_ids),
        ("date", ">=", date_from),
        ("date", "<=", date_to),
    ]

    line_ids = client.AccountMoveLine.search(domain, order="date asc, id asc")
    if not line_ids:
        print("No hi ha moviments per als filtres indicats.")

    fields = ["id", "date", "name", "ref", "debit", "credit"]
    rows = client.AccountMoveLine.read(line_ids, fields) if line_ids else []

    # Defensa extra: alguns backends no garanteixen l'ordre del read(line_ids, ...)
    rows = sorted(rows, key=lambda r: (to_text(r.get("date")), int(r.get("id") or 0)))

    with io.open(output_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(u"id;data;compte_comptable;descripcio;import\n")
        for row in rows:
            desc = classify_description(row.get("name"), row.get("ref"))
            signed = amount_signed(row.get("debit"), row.get("credit"))
            line = u"%s;%s;%s;%s;%s\n" % (
                to_text(row.get("id")),
                to_text(row.get("date")),
                account_code,
                desc.replace(u";", u","),
                format_amount(signed),
            )
            fh.write(line)

    print("CSV generat: %s (%s línies)" % (output_path, len(rows)))


def parse_args(argv):
    if argparse is None:
        raise RuntimeError("argparse no disponible")

    parser = argparse.ArgumentParser(
        description="Exporta account.move.line a CSV amb classificació de descripcions"
    )
    parser.add_argument("--account", required=True, help="Codi compte comptable (ex: 572000000005)")
    parser.add_argument("--date-from", required=True, help="Data inici (YYYY-MM-DD)")
    parser.add_argument("--date-to", required=True, help="Data fi (YYYY-MM-DD)")
    parser.add_argument("--output", required=True, help="Ruta fitxer CSV de sortida")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    export_csv(args.account, args.date_from, args.date_to, args.output)


if __name__ == "__main__":
    main()
