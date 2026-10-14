# -*- coding: utf-8 -*-
"""Proves de selecció i artefactes de l'obertura, sense ERP ni Odoo."""

from __future__ import print_function, unicode_literals

import csv
import errno
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

SCRIPT = Path(__file__).resolve().parents[1] / "export_opening_invoices.py"
SPEC = importlib.util.spec_from_file_location("export_opening_invoices", SCRIPT)
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


def invoice(invoice_id, residual, state="open", invoice_type="out_invoice"):
    return {
        "id": invoice_id,
        "number": "F;{}\nCatalà".format(invoice_id),
        "type": invoice_type,
        "state": state,
        "company_id": [1, "Empresa"],
        "partner_id": [2, "Tercer"],
        "account_id": [3, "Compte"],
        "currency_id": [4, "EUR"],
        "date_invoice": "2026-10-14",
        "date_due": "2026-11-14",
        "move_id": [invoice_id + 100, "Moviment"],
        "payment_ids": [],
        "amount_total": -100.0 if residual < 0 else 100.0,
        "residual": residual,
    }


class FakeReader:
    def __init__(self, invoices, agreements=None, installments=None):
        self.calls = []
        self.later_moves = []
        self.missing_reads = False
        self.has_installments = agreements is not None
        self.records = {
            exporter.INVOICE: invoices,
            exporter.AGREEMENT: agreements or [],
            exporter.INSTALLMENT: installments or [],
            "account.move.line": [],
            "account.account": [{"id": 3, "code": "430000", "name": "Clients"}],
        }

    def execute(self, model, method, *args):
        self.calls.append((model, method, args))
        if method == "search":
            if model == "account.move":
                return self.later_moves
            if model == "ir.model":
                return [1] if self.has_installments else []
            records = self.records[model]
            if model == exporter.INVOICE:
                records = [
                    row
                    for row in records
                    if row["state"] in {"open", "paid"} and row["residual"] != 0
                ]
            return [row["id"] for row in records]
        if method == "read":
            if self.missing_reads:
                return []
            return [row.copy() for row in self.records[model] if row["id"] in args[0]]
        raise AssertionError("Operació inesperada: {}".format(method))


class OpeningExtractionTest(unittest.TestCase):
    def test_main_uses_erppeek_and_dbconfig_for_the_full_export(self):
        config = {
            "server": "http://erp-proves:8069",
            "db": "erp_copia_assaig",
            "user": "proves",
            "password": "contrasenya-de-prova",
        }
        reader = FakeReader([invoice(1, 60)])
        factory = Mock(return_value=reader)
        modules = {
            "dbconfig": SimpleNamespace(erppeek=config),
            "erppeek": SimpleNamespace(Client=factory),
        }
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "snapshot"
            with patch.dict(sys.modules, modules), patch("builtins.print"):
                result = exporter.main(
                    [
                        "--cutoff",
                        "2026-10-14",
                        "--company-id",
                        "1",
                        "--snapshot-reference",
                        "copia-proves",
                        "--output",
                        str(output),
                    ]
                )
            self.assertEqual(result, 0)
            factory.assert_called_once_with(**config)
            payload = json.loads((output / "opening_invoices.json").read_text())
            self.assertEqual(payload["metadata"]["source_database"], config["db"])
            self.assertEqual(payload["invoices"][0]["id"], 1)
            self.assertNotIn(config["password"], json.dumps(payload))
            self.assertTrue(all(call[1] in {"search", "read"} for call in reader.calls))

    def test_partial_negative_refund_and_paid_anomaly_are_not_lost(self):
        reader = FakeReader(
            [
                invoice(1, 60),
                invoice(2, -25),
                invoice(3, 10, invoice_type="out_refund"),
                invoice(4, 0, state="paid"),
                invoice(5, 8, state="paid"),
                invoice(6, 70, state="draft"),
            ]
        )
        data = exporter.Extractor(reader, 1, batch_size=2).extract("2026-10-14")
        self.assertEqual([row["id"] for row in data["invoices"]], [1, 2, 3, 5])
        self.assertEqual(
            data["diagnostics"],
            [{"code": "paid_invoice_with_residual", "invoice_id": 5}],
        )
        self.assertTrue(all(call[1] in {"search", "read"} for call in reader.calls))
        domain = next(
            args[0]
            for model, method, args in reader.calls
            if model == exporter.INVOICE and method == "search"
        )
        self.assertIn(("company_id", "=", 1), domain)
        self.assertIn(("residual", "!=", 0), domain)

    def test_active_installments_keep_paid_zero_residual_invoice(self):
        agreement = {
            "id": 10,
            "invoice_id": [1, "F1"],
            "state": "parcialment_cobrat",
            "create_date": "2026-10-01 10:00:00",
            "move_id": [200, "Fraccionament"],
            "fraccionament_ids": [20],
            "import_no_cobrat": 60,
        }
        installment = {
            "id": 20,
            "move_line_id": False,
            "applied_move_line_id": False,
            "applied_move_id": False,
            "canceled_move_id": False,
            "state": "no_cobrat",
            "import": 60,
        }
        reader = FakeReader([invoice(1, 0, state="paid")], [agreement], [installment])
        data = exporter.Extractor(reader, 1).extract("2026-10-14")
        self.assertEqual(len(data["invoices"]), 1)
        self.assertEqual(data["installments"], [installment])
        self.assertEqual(data["diagnostics"][0]["code"], "installments_require_review")
        self.assertTrue(exporter.invoice_rows(data)[0]["has_active_installments"])

    def test_rejects_historical_cutoff_on_evolved_database(self):
        reader = FakeReader([])
        reader.later_moves = [99]
        with self.assertRaisesRegex(ValueError, "posteriors al tall"):
            exporter.Extractor(reader, 1).extract("2026-10-14")

    def test_rejects_partial_read_instead_of_exporting_incomplete_data(self):
        reader = FakeReader([invoice(1, 60)])
        reader.missing_reads = True
        with self.assertRaisesRegex(ValueError, "Lectura incompleta"):
            exporter.Extractor(reader, 1).extract("2026-10-14")

    def test_rejects_future_invoice(self):
        row = invoice(1, 60)
        row["date_invoice"] = "2026-10-15"
        with self.assertRaisesRegex(ValueError, "data vàlida"):
            exporter.Extractor(FakeReader([row]), 1).extract("2026-10-14")

    def test_writes_decimal_totals_csv_and_checksum_without_overwriting(self):
        reader = FakeReader([invoice(1, 0.1), invoice(2, 0.2)])
        data = exporter.Extractor(reader, 1).extract("2026-10-14")
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "snapshot"
            exporter.write_export(output, data, {"format_version": 1})
            raw = (output / "opening_invoices.json").read_bytes()
            payload = json.loads(raw)
            self.assertEqual(payload["invoice_residual_totals"][0]["residual"], "0.3")
            self.assertEqual(payload["invoices"][0]["id"], 1)
            checksum = (output / "opening_invoices.sha256").read_text().split()[0]
            self.assertEqual(checksum, hashlib.sha256(raw).hexdigest())
            with (output / "invoices.csv").open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream, delimiter=";"))
            self.assertEqual(rows[0]["number"], "F;1\nCatalà")
            with self.assertRaises(OSError) as caught:
                exporter.write_export(output, data, {})
            self.assertEqual(caught.exception.errno, errno.EEXIST)
            self.assertEqual((output / "opening_invoices.json").read_bytes(), raw)

    def test_currency_and_invoice_types_are_not_netted_together(self):
        rows = [
            invoice(1, 10),
            invoice(2, 20, invoice_type="out_refund"),
            invoice(3, 30),
        ]
        rows[2]["currency_id"] = [5, "USD"]
        data = exporter.Extractor(FakeReader(rows), 1).extract("2026-10-14")
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "snapshot"
            exporter.write_export(output, data, {})
            payload = json.loads((output / "opening_invoices.json").read_text())
            self.assertEqual(len(payload["invoice_residual_totals"]), 3)

    def test_rejects_non_finite_amounts(self):
        for value in (float("nan"), float("inf"), False):
            with self.subTest(value=value), self.assertRaises(ValueError):
                exporter.amount(value)


if __name__ == "__main__":
    unittest.main()
