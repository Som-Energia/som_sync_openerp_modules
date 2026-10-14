# -*- coding: utf-8 -*-
"""Extreu el punt de partida de les proves d'obertura des d'una còpia de l'ERP."""

from __future__ import print_function, unicode_literals

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xmlrpc.client import Error

INVOICE = "account.invoice"
AGREEMENT = "account.invoice.fraccionament"
INSTALLMENT = "account.invoice.fraccionament.fraccionaments"
ACTIVE_AGREEMENTS = {"no_cobrat", "parcialment_cobrat"}
INVOICE_FIELDS = [
    "number",
    "type",
    "state",
    "company_id",
    "partner_id",
    "account_id",
    "currency_id",
    "journal_id",
    "date_invoice",
    "date_due",
    "move_id",
    "amount_untaxed",
    "amount_tax",
    "amount_total",
    "residual",
    "payment_ids",
    "payment_term",
    "payment_type",
    "fiscal_position",
    "origin",
    "reference",
    "rectifying_id",
    "rectificative_type",
]
AGREEMENT_FIELDS = [
    "invoice_id",
    "company_id",
    "state",
    "create_date",
    "codi",
    "move_id",
    "import_a_fraccionar",
    "import_cobrat",
    "import_no_cobrat",
    "fraccionament_ids",
    "origin_account_id",
]
INSTALLMENT_FIELDS = [
    "invoice_fraccionament_id",
    "company_id",
    "state",
    "import",
    "data_venciment",
    "move_line_id",
    "applied_move_id",
    "applied_move_line_id",
    "canceled_move_id",
    "invoice_desti_id",
    "remesa_desti_id",
    "data_aplicacio",
]
MOVE_LINE_FIELDS = [
    "move_id",
    "account_id",
    "partner_id",
    "date",
    "date_maturity",
    "debit",
    "credit",
    "currency_id",
    "amount_currency",
    "reconcile_id",
    "reconcile_partial_id",
    "name",
    "ref",
]


def relation_id(value):
    """Normalitza un many2one XML-RPC sense confondre False amb un identificador."""
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def amount(value):
    """Conserva la precisió rebuda i rebutja imports invàlids."""
    if value is False or value is None:
        raise ValueError("Import absent en un registre de l'ERP")
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("Import invàlid: {!r}".format(value))
    if not result.is_finite():
        raise ValueError("Import no finit: {!r}".format(value))
    return result


class Extractor:
    """Recull registres originals i diagnòstics, sense decidir la seva importació."""

    def __init__(self, client, company_id, batch_size=200):
        self.client = client
        self.company_id = company_id
        self.batch_size = batch_size

    def search(self, model, domain, limit=None):
        return self.client.execute(model, "search", domain, 0, limit or False, "id asc")

    def read(self, model, ids, fields):
        rows = []
        ids = sorted(set(ids))
        for offset in range(0, len(ids), self.batch_size):
            batch = ids[offset: offset + self.batch_size]
            result = self.client.execute(model, "read", batch, fields)
            if {row["id"] for row in result} != set(batch):
                raise ValueError("Lectura incompleta de {}; revisa els permisos".format(model))
            rows.extend(result)
        return sorted(rows, key=lambda row: row["id"])

    def extract(self, cutoff):
        company = [("company_id", "=", self.company_id)]
        later_moves = self.search(
            "account.move",
            company + [("state", "=", "posted"), ("date", ">", cutoff)],
            limit=1,
        )
        if later_moves:
            raise ValueError(
                "Hi ha assentaments comptabilitzats posteriors al tall. "
                "Cal una còpia de l'ERP del tall; no es reconstrueix l'històric."
            )
        model_ids = self.search("ir.model", [("model", "=", AGREEMENT)])
        agreements = []
        if model_ids:
            agreements = self.read(
                AGREEMENT, self.search(AGREEMENT, company), AGREEMENT_FIELDS
            )
        active_invoice_ids = {
            relation_id(row["invoice_id"])
            for row in agreements
            if row["state"] in ACTIVE_AGREEMENTS
        }
        if None in active_invoice_ids:
            raise ValueError("Hi ha un acord actiu sense factura d'origen")
        invoice_ids = self.search(
            INVOICE,
            company + [("state", "in", ["open", "paid"]), ("residual", "!=", 0)],
        )
        invoices = self.read(
            INVOICE, list(set(invoice_ids) | active_invoice_ids), INVOICE_FIELDS
        )
        for invoice in invoices:
            if relation_id(invoice["company_id"]) != self.company_id:
                raise ValueError("Un acord apunta a una factura d'una altra empresa")
            if not invoice["date_invoice"] or invoice["date_invoice"] > cutoff:
                raise ValueError("Factura {} sense data vàlida al tall".format(invoice["id"]))
            amount(invoice["residual"])
            amount(invoice["amount_total"])
        selected_ids = {row["id"] for row in invoices}
        agreements = [
            row for row in agreements if relation_id(row["invoice_id"]) in selected_ids
        ]
        if any(row["create_date"][:10] > cutoff for row in agreements):
            raise ValueError("Hi ha acords creats després del tall; revisa la còpia")
        installments = self.read(
            INSTALLMENT,
            [line_id for row in agreements for line_id in row["fraccionament_ids"]],
            INSTALLMENT_FIELDS,
        )
        move_ids = {relation_id(row["move_id"]) for row in invoices + agreements}
        line_ids = {line_id for row in invoices for line_id in row["payment_ids"]}
        for row in installments:
            move_ids.update(
                relation_id(row[field])
                for field in ("applied_move_id", "canceled_move_id")
            )
            line_ids.update(
                relation_id(row[field])
                for field in ("move_line_id", "applied_move_line_id")
            )
        move_ids = sorted(move_ids - {None})
        for offset in range(0, len(move_ids), self.batch_size):
            batch = move_ids[offset: offset + self.batch_size]
            line_ids.update(
                self.search("account.move.line", [("move_id", "in", batch)])
            )
        move_lines = self.read(
            "account.move.line", list(line_ids - {None}), MOVE_LINE_FIELDS
        )
        account_ids = {
            relation_id(row["account_id"]) for row in invoices + move_lines
        } - {None}
        accounts = self.read(
            "account.account", list(account_ids), ["code", "name", "type", "reconcile"]
        )
        diagnostics = [
            {
                "code": "installments_require_review",
                "invoice_id": invoice_id,
                "message": "No sumar quotes i residual sense validar els traspassos.",
            }
            for invoice_id in sorted(active_invoice_ids)
        ]
        for row in invoices:
            if row["state"] not in {"open", "paid"} or not row["move_id"]:
                diagnostics.append(
                    {"code": "invoice_requires_review", "invoice_id": row["id"]}
                )
            if row["state"] == "paid" and amount(row["residual"]) != 0:
                diagnostics.append(
                    {"code": "paid_invoice_with_residual", "invoice_id": row["id"]}
                )
        return {
            "invoices": invoices,
            "agreements": agreements,
            "installments": installments,
            "move_lines": move_lines,
            "accounts": accounts,
            "diagnostics": diagnostics,
            "installment_model_available": bool(model_ids),
        }


def invoice_rows(data):
    """Construeix el control de residuals sense agregar deutes de fraccionaments."""
    accounts = {row["id"]: row for row in data["accounts"]}
    active_ids = {
        relation_id(row["invoice_id"])
        for row in data["agreements"]
        if row["state"] in ACTIVE_AGREEMENTS
    }
    rows = []
    for invoice in data["invoices"]:
        account_id = relation_id(invoice["account_id"])
        rows.append(
            {
                "erp_invoice_id": invoice["id"],
                "number": invoice["number"],
                "type": invoice["type"],
                "state": invoice["state"],
                "partner_id": relation_id(invoice["partner_id"]),
                "account_id": account_id,
                "account_code": accounts.get(account_id, {}).get("code", ""),
                "currency_id": relation_id(invoice["currency_id"]),
                "date_invoice": invoice["date_invoice"],
                "date_due": invoice["date_due"],
                "original_total": str(amount(invoice["amount_total"])),
                "invoice_residual": str(amount(invoice["residual"])),
                "has_active_installments": invoice["id"] in active_ids,
            }
        )
    return rows


def write_export(output, data, metadata):
    """Crea una extracció nova; mai sobreescriu una foto anterior."""
    rows = invoice_rows(data)
    totals = defaultdict(Decimal)
    for row in rows:
        key = (row["type"], row["currency_id"], row["account_id"], row["partner_id"])
        totals[key] += amount(row["invoice_residual"])
    data = dict(data)
    data["metadata"] = metadata
    data["invoice_residual_totals"] = [
        {
            "type": total_key[0],
            "currency_id": total_key[1],
            "account_id": total_key[2],
            "partner_id": total_key[3],
            "residual": str(value),
        }
        for total_key, value in sorted(totals.items(), key=lambda item: str(item[0]))
    ]
    content = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    output.mkdir()
    (output / "opening_invoices.json").write_text(content, encoding="utf-8")
    (output / "opening_invoices.sha256").write_text(
        hashlib.sha256(content.encode("utf-8")).hexdigest()
        + "  opening_invoices.json\n",
        encoding="utf-8",
    )
    fieldnames = list(rows[0]) if rows else ["erp_invoice_id", "invoice_residual"]
    with (output / "invoices.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cutoff", required=True, type=date.fromisoformat)
    parser.add_argument("--company-id", required=True, type=int)
    parser.add_argument(
        "--snapshot-reference",
        required=True,
        help="Identificador de la còpia consistent de l'ERP",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Directori nou, amb el directori pare ja existent",
    )
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args(argv)
    if args.company_id <= 0 or args.batch_size <= 0:
        parser.error("company-id i batch-size han de ser positius")
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error("output ha de ser un directori nou amb un pare existent")
    return args


def main(argv=None):
    args = parse_args(argv)
    try:
        import dbconfig
        from erppeek import Client

        started = datetime.now(timezone.utc).isoformat()
        client = Client(**dbconfig.erppeek)
        data = Extractor(client, args.company_id, args.batch_size).extract(
            args.cutoff.isoformat()
        )
        write_export(
            args.output,
            data,
            {
                "format_version": 1,
                "cutoff": args.cutoff.isoformat(),
                "snapshot_reference": args.snapshot_reference,
                "company_id": args.company_id,
                "source_database": dbconfig.erppeek["db"],
                "extraction_started_at": started,
                "extraction_finished_at": datetime.now(timezone.utc).isoformat(),
                "scope": "invoice_residuals_and_related_installments",
                "ready_for_import": False,
            },
        )
    except KeyError as exc:
        print("Falta la clau de configuració {}".format(exc.args[0]), file=sys.stderr)
        return 1
    except (ImportError, ValueError, OSError, RuntimeError, Error) as exc:
        print("No s'ha pogut completar l'extracció: {}".format(exc), file=sys.stderr)
        return 1
    print(
        "Extracció: {}; factures: {}; diagnòstics: {}".format(
            args.output, len(data["invoices"]), len(data["diagnostics"])
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
