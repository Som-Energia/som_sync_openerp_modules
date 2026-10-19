# -*- coding: utf-8 -*-
"""Exporta els saldos natius de l'ERP dels comptes de 12 dígits, fins a hui."""

from __future__ import print_function, unicode_literals

import argparse
import logging
import os
import re
import sys
from datetime import date
try:
    from http.client import HTTPException
    from xmlrpc.client import Error
except ImportError:
    from httplib import HTTPException
    from xmlrpclib import Error

from opening_common import parse_date, print_message, text, write_csv
from opening_01_export_invoices import amount, relation_id

logger = logging.getLogger(__name__)

ACCOUNT = "account.account"
FISCALYEAR = "account.fiscalyear"
ACCOUNT_CODE = re.compile(r"^[0-9]{12}\Z")
BALANCE_FIELDS = ["code", "name", "company_id", "odoo_account_code", "debit", "credit", "balance"]
CSV_FIELDS = ["company_id", "fiscalyear_id", "date_to", "account_id", "code", "name",
              "odoo_account_code", "debit", "credit", "balance"]


class Extractor(object):
    def __init__(self, client, company_id, date_to, batch_size=200):
        if company_id <= 0 or batch_size <= 0:
            raise ValueError("company-id i batch-size han de ser positius")
        self.client = client
        self.company_id = company_id
        self.date_to = parse_date(date_to).isoformat()
        self.batch_size = batch_size

    def search(self, model, domain, order="id asc", context=None):
        return self.client.execute(model, "search", domain, 0, False, order, context or {})

    def read(self, model, ids, fields, context=None):
        rows = self.client.execute(model, "read", ids, fields, context or {})
        if len(rows) != len(ids) or {row["id"] for row in rows} != set(ids):
            raise ValueError(
                "Lectura incompleta o duplicada de {}; revisa els permisos".format(model))
        return rows

    def fiscalyear(self):
        domain = [("date_start", "<=", self.date_to), ("date_stop", ">=", self.date_to)]
        ids = self.search(FISCALYEAR, domain + [("company_id", "=", self.company_id)])
        if not ids:
            # L'ERP també permet exercicis compartits, sense empresa assignada.
            ids = self.search(FISCALYEAR, domain + [("company_id", "=", False)])
        if len(ids) != 1:
            raise ValueError(
                "Cal un únic exercici per a l'empresa {} i la data {}; trobats {}".format(
                    self.company_id, self.date_to, len(ids)))
        year = self.read(FISCALYEAR, ids, ["name", "company_id", "date_start", "date_stop"])[0]
        if (relation_id(year["company_id"]) not in (None, self.company_id)
                or not year["date_start"] <= self.date_to <= year["date_stop"]):
            raise ValueError("L'exercici ha canviat durant la lectura; revisa la còpia ERP")
        return year

    def extract(self, progress_factory):
        year = self.fiscalyear()
        context = {"active_test": False, "fiscalyear": year["id"],
                   "date_from": year["date_start"], "date_to": self.date_to, "state": "bydate"}
        logger.info("Exercici %s (ID %s); empresa %s; des de %s fins a %s",
                    year["name"], year["id"], self.company_id, year["date_start"], self.date_to)
        # =like conserva el patró de 12 caràcters en l'ORM antic; el regex exigeix dígits ASCII.
        candidate_ids = self.search(ACCOUNT, [("company_id", "=", self.company_id),
                                              ("code", "=like", "_" * 12)],
                                    order="code asc, id asc", context={"active_test": False})
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("La cerca ha retornat comptes duplicats")
        logger.info("Llegint els codis de %s comptes candidats", len(candidate_ids))
        accounts = []
        for offset in range(0, len(candidate_ids), self.batch_size):
            records = self.read(ACCOUNT, candidate_ids[offset:offset + self.batch_size], ["code"],
                                context={"active_test": False})
            accounts.extend(row for row in records if ACCOUNT_CODE.match(text(row["code"] or "")))
        accounts.sort(key=lambda row: (row["code"], row["id"]))
        logger.info("Seleccionats %s comptes de 12 dígits; calculant saldos per lots de %s",
                    len(accounts), self.batch_size)
        rows = []
        with progress_factory(total=len(accounts), desc="Calculant saldos", unit="compte",
                              file=sys.stderr, ascii=True) as progress:
            for offset in range(0, len(accounts), self.batch_size):
                batch = accounts[offset:offset + self.batch_size]
                records = self.read(ACCOUNT, [row["id"] for row in batch], BALANCE_FIELDS, context)
                by_id = {row["id"]: row for row in records}
                batch_rows = []
                for original in batch:
                    row = by_id[original["id"]]
                    if (row["code"] != original["code"]
                            or relation_id(row["company_id"]) != self.company_id):
                        raise ValueError(
                            "El compte {} ha canviat de codi o d'empresa".format(row["id"]))
                    result = {"company_id": self.company_id, "fiscalyear_id": year["id"],
                              "date_to": self.date_to, "account_id": row["id"],
                              "code": text(row["code"]), "name": text(row["name"] or ""),
                              "odoo_account_code": text(row["odoo_account_code"] or "")}
                    # Preservem els tres camps calculats per l'ERP, sense reconstruir el saldo.
                    result.update({field: str(amount(row[field]))
                                   for field in ("debit", "credit", "balance")})
                    batch_rows.append(result)
                rows.extend(batch_rows)
                progress.update(len(batch_rows))
        return rows


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--company-id", required=True, type=int)
    parser.add_argument("--output", required=True, type=text, help="Fitxer CSV nou de sortida")
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args(argv)
    if args.company_id <= 0 or args.batch_size <= 0:
        parser.error("company-id i batch-size han de ser positius")
    parent = os.path.dirname(os.path.abspath(args.output))
    if os.path.exists(args.output) or not os.path.isdir(parent):
        parser.error("output ha de ser un fitxer nou amb un directori pare existent")
    return args


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    try:
        import dbconfig
        from erppeek import Client
        from tqdm import tqdm

        date_to = date.today().isoformat()
        logger.info("Connectant a l'ERP amb erppeek; data del saldo: %s", date_to)
        client = Client(**dbconfig.erppeek)
        rows = Extractor(client, args.company_id, date_to, args.batch_size).extract(tqdm)
        write_csv(args.output, CSV_FIELDS, rows)
    except (ImportError, KeyError, ValueError, IOError, OSError,
            RuntimeError, Error, HTTPException) as exc:
        print_message("No s'ha pogut completar l'exportació de saldos: {}".format(
            exc), file=sys.stderr)
        return 1
    missing = sum(not row["odoo_account_code"] for row in rows)
    zero = sum(amount(row["balance"]) == 0 for row in rows)
    print_message("CSV generat: {}; {} comptes; {} amb saldo zero; {} sense codi Odoo".format(
        args.output, len(rows), zero, missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
