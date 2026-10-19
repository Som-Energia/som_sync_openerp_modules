# -*- coding: utf-8 -*-
"""Fase 1: identifica factures obertes i genera IDs ERP i un CSV de control."""

from __future__ import print_function, unicode_literals

import argparse
import logging
import os
import sys
from decimal import Decimal, InvalidOperation
try:
    from xmlrpc.client import Error
except ImportError:
    from xmlrpclib import Error

from opening_common import (
    is_integer, parse_date, print_message, text, utc_now, write_csv, write_json,
)

logger = logging.getLogger(__name__)

INVOICE = "account.invoice"
INVOICE_SCOPE_TYPES = {
    "customers": ["out_invoice", "out_refund"],
    "suppliers": ["in_invoice", "in_refund"],
    "all": ["out_invoice", "out_refund", "in_invoice", "in_refund"],
}
INVOICE_FIELDS = [
    "number", "type", "state", "company_id", "partner_id", "currency_id",
    "journal_id", "date_invoice", "date_due", "amount_total", "residual",
]
CSV_FIELDS = [
    "erp_invoice_id", "number", "type", "state", "partner_id", "currency_id",
    "journal_id", "date_invoice", "date_due", "original_total", "invoice_residual",
]


def relation_id(value):
    """Normalitza un many2one retornat per erppeek."""
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value if is_integer(value) else None


def amount(value):
    """Conserva la precisió rebuda i rebutja imports absents o no finits."""
    if value is False or value is None:
        raise ValueError("Import absent en un registre de l'ERP")
    try:
        result = Decimal(repr(value) if isinstance(value, float) else str(value))
    except InvalidOperation:
        raise ValueError("Import invàlid: {!r}".format(value))
    if not result.is_finite():
        raise ValueError("Import no finit: {!r}".format(value))
    return result


class Extractor(object):
    """Consulta únicament diaris i capçaleres de factures per identificar IDs."""

    def __init__(self, client, company_id, batch_size=200, invoice_scope="all"):
        if invoice_scope not in INVOICE_SCOPE_TYPES:
            raise ValueError("Abast de factures desconegut: {}".format(invoice_scope))
        if company_id <= 0 or batch_size <= 0:
            raise ValueError("L'empresa i la mida del lot han de ser positives")
        self.client = client
        self.company_id = company_id
        self.batch_size = batch_size
        self.invoice_scope = invoice_scope

    def search(self, model, domain):
        logger.info("Cercant registres de %s...", model)
        ids = self.client.execute(model, "search", domain, 0, False, "id asc")
        logger.info("%s: %s registres trobats", model, len(ids))
        return sorted(set(ids))

    def read_invoices(self, ids):
        rows = []
        logger.info("Llegint %s capçaleres de factura, en lots de %s", len(ids), self.batch_size)
        for offset in range(0, len(ids), self.batch_size):
            batch = ids[offset: offset + self.batch_size]
            logger.info("Factures: llegint registres %s-%s de %s...",
                        offset + 1, offset + len(batch), len(ids))
            result = self.client.execute(INVOICE, "read", batch, INVOICE_FIELDS)
            if len(result) != len(batch) or {row["id"] for row in result} != set(batch):
                raise ValueError("Lectura incompleta o duplicada de factures; revisa els permisos")
            rows.extend(result)
            logger.info("Factures: %s/%s capçaleres llegides", len(rows), len(ids))
        return sorted(rows, key=lambda row: row["id"])

    def extract(self, reference_date):
        logger.info("Identificant factures amb pendent actual: empresa %s; referència %s; abast %s",
                    self.company_id, reference_date, self.invoice_scope)
        journal_ids = self.search("account.journal", [("som_sync_odoo_invoices", "=", True)])
        invoice_types = INVOICE_SCOPE_TYPES[self.invoice_scope]
        invoice_ids = self.search(INVOICE, [
            ("company_id", "=", self.company_id),
            ("state", "=", "open"),
            ("residual", "!=", 0),
            ("type", "in", invoice_types),
            ("journal_id", "in", journal_ids),
        ]) if journal_ids else []
        invoices = self.read_invoices(invoice_ids)
        diagnostics = []
        for inv in invoices:
            if (relation_id(inv["company_id"]) != self.company_id
                    or inv["state"] != "open" or inv["type"] not in invoice_types
                    or relation_id(inv["journal_id"]) not in journal_ids
                    or amount(inv["residual"]) == 0):
                raise ValueError("La factura {} no compleix la selecció; revisa la còpia ERP"
                                 .format(inv["id"]))
            amount(inv["amount_total"])
            if not inv["date_invoice"]:
                diagnostics.append({"code": "missing_invoice_date", "invoice_id": inv["id"]})
        logger.info("Identificació completada: %s factures; %s diagnòstics",
                    len(invoices), len(diagnostics))
        return {"invoices": invoices, "journal_ids": journal_ids, "diagnostics": diagnostics}


def invoice_rows(data):
    """Una fila de control per factura, amb imports decimals com a text."""
    return [{
        "erp_invoice_id": inv["id"], "number": inv["number"], "type": inv["type"],
        "state": inv["state"], "partner_id": relation_id(inv["partner_id"]),
        "currency_id": relation_id(inv["currency_id"]),
        "journal_id": relation_id(inv["journal_id"]),
        "date_invoice": inv["date_invoice"], "date_due": inv["date_due"],
        "original_total": str(amount(inv["amount_total"])),
        "invoice_residual": str(amount(inv["residual"])),
    } for inv in sorted(data["invoices"], key=lambda row: row["id"])]


def control_totals(rows):
    """Agrupa recomptes i imports sense barrejar tipus ni monedes."""
    totals = {}
    for row in rows:
        key = (row["type"], row["currency_id"])
        group = totals.setdefault(key, {"invoice_count": 0, "original_total": Decimal(0),
                                        "residual": Decimal(0)})
        group["invoice_count"] += 1
        group["original_total"] += amount(row["original_total"])
        group["residual"] += amount(row["invoice_residual"])
    return [{
        "type": group_key[0], "currency_id": group_key[1],
        "invoice_count": values["invoice_count"],
        "original_total": str(values["original_total"]), "residual": str(values["residual"]),
    } for group_key, values in sorted(totals.items(), key=lambda item: str(item[0]))]


def write_export(output, data, metadata):
    """Genera els dos fitxers de la fase 1 en un directori nou."""
    rows = invoice_rows(data)
    ids = [row["erp_invoice_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("La selecció conté IDs de factura duplicats")
    export_metadata = dict(metadata)
    export_metadata.update({"format_version": 1, "phase": "identify_invoice_ids",
                            "model": INVOICE, "invoice_count": len(ids),
                            "journal_ids": data["journal_ids"]})
    totals = control_totals(rows)
    payload = {"metadata": export_metadata, "invoice_ids": ids,
               "control_totals": totals, "diagnostics": data["diagnostics"]}
    logger.info("Creant el directori de sortida %s", output)
    os.mkdir(output)
    json_path = os.path.join(output, "invoice_ids.json")
    csv_path = os.path.join(output, "invoices.csv")
    logger.info("Escrivint %s (%s IDs)", json_path, len(ids))
    write_json(json_path, payload)
    logger.info("Escrivint %s (%s factures)", csv_path, len(rows))
    write_csv(csv_path, CSV_FIELDS, rows)
    for total in totals:
        logger.info("Control %s, moneda %s: %s factures; total original %s; pendent %s",
                    total["type"], total["currency_id"], total["invoice_count"],
                    total["original_total"], total["residual"])
    logger.info("Fitxers de la fase 1 generats a %s", output)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reference-date", "--cutoff", dest="reference_date", required=True,
        type=parse_date,
        help="Data de referència de l'assaig (YYYY-MM-DD); no filtra ni calcula històrics",
    )
    parser.add_argument("--company-id", required=True, type=int)
    parser.add_argument(
        "--invoice-scope", choices=["customers", "suppliers", "all"], default="all",
        help="Abast: customers (clients), suppliers (proveïdors), all (tots, per defecte)",
    )
    parser.add_argument("--snapshot-reference", required=True,
                        help="Identificador de la còpia consistent de l'ERP")
    parser.add_argument("--output", required=True, type=text,
                        help="Directori nou, amb el directori pare ja existent")
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args(argv)
    if args.company_id <= 0 or args.batch_size <= 0:
        parser.error("company-id i batch-size han de ser positius")
    parent = os.path.dirname(os.path.abspath(args.output))
    if os.path.exists(args.output) or not os.path.isdir(parent):
        parser.error("output ha de ser un directori nou amb un pare existent")
    return args


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    try:
        import dbconfig
        from erppeek import Client

        started = utc_now()
        logger.info("Connectant a l'ERP amb erppeek...")
        client = Client(**dbconfig.erppeek)
        logger.info("Connexió amb l'ERP establerta")
        data = Extractor(client, args.company_id, args.batch_size,
                         invoice_scope=args.invoice_scope).extract(args.reference_date.isoformat())
        write_export(args.output, data, {
            "reference_date": args.reference_date.isoformat(),
            "cutoff": args.reference_date.isoformat(), "residual_basis": "current_erp_state",
            "snapshot_reference": args.snapshot_reference, "company_id": args.company_id,
            "invoice_scope": args.invoice_scope,
            "invoice_types": INVOICE_SCOPE_TYPES[args.invoice_scope],
            "selection": {"state": "open", "residual_nonzero": True,
                          "only_sync_enabled_journals": True},
            "source_database": dbconfig.erppeek["db"],
            "extraction_started_at": started,
            "extraction_finished_at": utc_now(),
        })
    except KeyError as exc:
        print_message("Falta la clau de dades o configuració {}".format(
            exc.args[0]), file=sys.stderr)
        return 1
    except (ImportError, ValueError, IOError, OSError, RuntimeError, Error) as exc:
        print_message("No s'ha pogut completar la identificació: {}".format(exc), file=sys.stderr)
        return 1
    print_message("Fase 1 completada: {}; {} IDs de factura".format(
        args.output, len(data["invoices"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
