# -*- coding: utf-8 -*-
"""Fase 3: identifica acords pendents i conserva totes les quotes per revisar-les."""

from __future__ import print_function, unicode_literals

import argparse
import logging
import os
import sys
from decimal import Decimal
try:
    from xmlrpc.client import Error
except ImportError:
    from xmlrpclib import Error

from opening_common import parse_date, print_message, text, utc_now, write_csv, write_json

from opening_01_export_invoices import (
    Extractor as InvoiceExtractor, INVOICE_SCOPE_TYPES, amount, relation_id,
)

logger = logging.getLogger(__name__)

AGREEMENT = "account.invoice.fraccionament"
LINE = "account.invoice.fraccionament.fraccionaments"
PENDING_STATES = ["no_cobrat", "parcialment_cobrat"]
AGREEMENT_FIELDS = ["invoice_id", "company_id", "codi", "state", "import_a_fraccionar"]
LINE_RELATIONS = [
    "move_line_id", "invoice_desti_id", "remesa_desti_id", "applied_move_id",
    "applied_move_line_id", "canceled_move_id", "agrupacio_move_id",
]
LINE_FIELDS = ["invoice_fraccionament_id", "company_id", "import", "state",
               "data_venciment", "data_aplicacio"] + LINE_RELATIONS
AGREEMENT_CSV_FIELDS = [
    "erp_fraccionament_id", "codi", "state", "amount_total", "erp_invoice_id",
    "invoice_number", "invoice_type", "invoice_state", "partner_id", "currency_id",
    "journal_id", "original_total", "invoice_residual",
]
LINE_CSV_FIELDS = [
    "erp_line_id", "erp_fraccionament_id", "erp_invoice_id", "invoice_type", "currency_id",
    "amount", "state", "date_due", "application_date",
] + LINE_RELATIONS


class Extractor(InvoiceExtractor):
    """Reutilitza les lectures per lots de factures, sense els filtres de fase 1."""

    def read_records(self, model, ids, fields):
        rows = []
        for offset in range(0, len(ids), self.batch_size):
            batch = ids[offset: offset + self.batch_size]
            logger.info("%s: llegint registres %s-%s de %s", model,
                        offset + 1, offset + len(batch), len(ids))
            result = self.client.execute(model, "read", batch, fields)
            if len(result) != len(batch) or {row["id"] for row in result} != set(batch):
                raise ValueError("Lectura incompleta o duplicada de {}; revisa els permisos".format(
                    model))
            rows.extend(result)
        return sorted(rows, key=lambda row: row["id"])

    def extract(self, reference_date):
        logger.info("Identificant acords pendents: empresa %s; referència %s; abast %s",
                    self.company_id, reference_date, self.invoice_scope)
        journal_ids = self.search("account.journal", [("som_sync_odoo_invoices", "=", True)])
        agreement_ids = self.search(AGREEMENT, [
            ("company_id", "=", self.company_id), ("state", "in", PENDING_STATES),
        ]) if journal_ids else []
        agreements = self.read_records(AGREEMENT, agreement_ids, AGREEMENT_FIELDS)
        for row in agreements:
            if (relation_id(row["company_id"]) != self.company_id
                    or row["state"] not in PENDING_STATES or not relation_id(row["invoice_id"])):
                raise ValueError(
                    "L'acord {} ha canviat o no té factura associada".format(row["id"]))
        invoice_ids = sorted({relation_id(row["invoice_id"]) for row in agreements})
        invoices = {row["id"]: row for row in self.read_invoices(invoice_ids)}
        selected = []
        for row in agreements:
            invoice = invoices[relation_id(row["invoice_id"])]
            if (relation_id(invoice["company_id"]) == self.company_id
                    and invoice["type"] in INVOICE_SCOPE_TYPES[self.invoice_scope]
                    and relation_id(invoice["journal_id"]) in journal_ids):
                amount(row["import_a_fraccionar"])
                amount(invoice["amount_total"])
                amount(invoice["residual"])
                selected.append(row)
        agreement_ids = [row["id"] for row in selected]
        line_ids = []
        for offset in range(0, len(agreement_ids), self.batch_size):
            line_ids.extend(self.search(LINE, [
                ("invoice_fraccionament_id", "in", agreement_ids[offset:offset + self.batch_size]),
            ]))
        if len(line_ids) != len(set(line_ids)):
            raise ValueError("Quotes duplicades entre lots; revisa la còpia ERP")
        lines = self.read_records(LINE, sorted(line_ids), LINE_FIELDS)
        selected_ids = set(agreement_ids)
        diagnostics = []
        for row in lines:
            if (relation_id(row["invoice_fraccionament_id"]) not in selected_ids
                    or relation_id(row["company_id"]) != self.company_id):
                raise ValueError("La quota {} ha canviat d'acord o d'empresa".format(row["id"]))
            amount(row["import"])
            if not row["data_venciment"]:
                diagnostics.append({"code": "missing_due_date", "line_id": row["id"]})
            if row["state"] == "cobrat" and not row["data_aplicacio"]:
                diagnostics.append({"code": "paid_without_application_date", "line_id": row["id"]})
        with_lines = {relation_id(row["invoice_fraccionament_id"]) for row in lines}
        for row in selected:
            if row["id"] not in with_lines:
                diagnostics.append({"code": "agreement_without_lines",
                                   "fraccionament_id": row["id"]})
        invoice_ids = sorted({relation_id(row["invoice_id"]) for row in selected})
        outside_count = sum(invoices[invoice_id]["state"] != "open"
                            or amount(invoices[invoice_id]["residual"]) == 0
                            for invoice_id in invoice_ids)
        logger.info("Identificació completada: %s acords; %s factures; %s quotes",
                    len(selected), len(invoice_ids), len(lines))
        logger.info("Informatiu: %s factures fora dels filtres d'estat/residual de fase 1",
                    outside_count)
        return {"agreements": selected, "invoices": {key: invoices[key] for key in invoice_ids},
                "lines": lines, "journal_ids": journal_ids, "diagnostics": diagnostics,
                "invoices_outside_phase_one_count": outside_count}


def control_rows(data):
    agreements, lines = [], []
    agreement_invoices = {}
    for row in data["agreements"]:
        invoice_id = relation_id(row["invoice_id"])
        agreement_invoices[row["id"]] = invoice_id
        invoice = data["invoices"][invoice_id]
        agreements.append({
            "erp_fraccionament_id": row["id"], "codi": row["codi"], "state": row["state"],
            "amount_total": str(amount(row["import_a_fraccionar"])), "erp_invoice_id": invoice_id,
            "invoice_number": invoice["number"], "invoice_type": invoice["type"],
            "invoice_state": invoice["state"], "partner_id": relation_id(invoice["partner_id"]),
            "currency_id": relation_id(invoice["currency_id"]),
            "journal_id": relation_id(invoice["journal_id"]),
            "original_total": str(amount(invoice["amount_total"])),
            "invoice_residual": str(amount(invoice["residual"])),
        })
    for row in data["lines"]:
        agreement_id = relation_id(row["invoice_fraccionament_id"])
        invoice_id = agreement_invoices[agreement_id]
        invoice = data["invoices"][invoice_id]
        line = {"erp_line_id": row["id"], "erp_fraccionament_id": agreement_id,
                "erp_invoice_id": invoice_id, "invoice_type": invoice["type"],
                "currency_id": relation_id(invoice["currency_id"]),
                "amount": str(amount(row["import"])), "state": row["state"],
                "date_due": row["data_venciment"] or "",
                "application_date": row["data_aplicacio"] or ""}
        line.update({field: relation_id(row[field]) for field in LINE_RELATIONS})
        lines.append(line)
    return agreements, lines


def control_totals(lines):
    totals = {}
    for row in lines:
        key = (row["invoice_type"], row["currency_id"], row["state"])
        group = totals.setdefault(key, {"line_count": 0, "amount": Decimal(0)})
        group["line_count"] += 1
        group["amount"] += amount(row["amount"])
    return [{"invoice_type": group_key[0], "currency_id": group_key[1], "state": group_key[2],
             "line_count": values["line_count"], "amount": str(values["amount"])}
            for group_key, values in sorted(totals.items(), key=lambda item: str(item[0]))]


def write_export(output, data, metadata):
    agreements, lines = control_rows(data)
    export_metadata = dict(metadata)
    export_metadata.update({"format_version": 1, "phase": "identify_fraccionament_ids",
                            "model": AGREEMENT, "fraccionament_count": len(agreements),
                            "invoice_count": len(data["invoices"]), "line_count": len(lines),
                            "invoices_outside_phase_one_count":
                                data["invoices_outside_phase_one_count"],
                            "journal_ids": data["journal_ids"]})
    payload = {"metadata": export_metadata,
               "fraccionament_ids": [row["erp_fraccionament_id"] for row in agreements],
               "invoice_ids": sorted(data["invoices"]),
               "control_totals": control_totals(lines), "diagnostics": data["diagnostics"]}
    os.mkdir(output)
    write_json(os.path.join(output, "fraccionament_ids.json"), payload)
    for filename, fields, rows in [("fraccionaments.csv", AGREEMENT_CSV_FIELDS, agreements),
                                   ("fraccionament_lines.csv", LINE_CSV_FIELDS, lines)]:
        path = os.path.join(output, filename)
        logger.info("Escrivint %s (%s registres)", path, len(rows))
        write_csv(path, fields, rows)
    logger.info("Manifest i CSV de control generats a %s", output)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-date", "--cutoff", dest="reference_date", required=True,
                        type=parse_date, help="Referència de l'assaig; no filtra dates")
    parser.add_argument("--company-id", required=True, type=int)
    parser.add_argument("--invoice-scope", choices=["customers", "suppliers", "all"], default="all")
    parser.add_argument("--snapshot-reference", required=True)
    parser.add_argument("--output", required=True, type=text, help="Directori de sortida nou")
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
        data = Extractor(client, args.company_id, args.batch_size, args.invoice_scope).extract(
            args.reference_date.isoformat())
        write_export(args.output, data, {
            "reference_date": args.reference_date.isoformat(),
            "cutoff": args.reference_date.isoformat(),
            "snapshot_reference": args.snapshot_reference, "company_id": args.company_id,
            "invoice_scope": args.invoice_scope, "source_database": dbconfig.erppeek["db"],
            "selection": {"agreement_states": PENDING_STATES, "only_sync_enabled_journals": True,
                          "invoice_types": INVOICE_SCOPE_TYPES[args.invoice_scope],
                          "invoice_state_filter": None, "invoice_residual_filter": None,
                          "all_line_states": True},
            "extraction_started_at": started,
            "extraction_finished_at": utc_now(),
        })
    except (ImportError, KeyError, ValueError, IOError, OSError, RuntimeError, Error) as exc:
        print_message("No s'ha pogut completar l'extracció de fraccionaments: {}".format(exc),
                      file=sys.stderr)
        return 1
    print_message("Fase 3 completada: {}; {} acords; {} quotes".format(
        args.output, len(data["agreements"]), len(data["lines"])))
    print_message("Informatiu: {} factures fora dels filtres d'estat/residual de fase 1".format(
        data["invoices_outside_phase_one_count"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
