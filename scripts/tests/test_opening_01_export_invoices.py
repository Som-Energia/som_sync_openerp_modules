# -*- coding: utf-8 -*-
"""Proves de la fase 1: selecció d'IDs i control, sense connexió a l'ERP."""

from __future__ import print_function, unicode_literals

import csv
import errno
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

SCRIPT = Path(__file__).resolve().parents[1] / "opening_01_export_invoices.py"
SPEC = importlib.util.spec_from_file_location("opening_01_export_invoices", SCRIPT)
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


def invoice(invoice_id, residual=60, state="open", invoice_type="out_invoice"):
    return {
        "id": invoice_id, "number": "F;{}\nCatalà".format(invoice_id),
        "type": invoice_type, "state": state, "company_id": [1, "Empresa"],
        "partner_id": [2, "Tercer"], "currency_id": [4, "EUR"],
        "journal_id": [7, "Diari habilitat"], "date_invoice": "2026-10-15",
        "date_due": "2026-11-14", "amount_total": 100, "residual": residual,
        "payment_ids": [99], "invoice_fraccionament_ids": [88],
    }


class FakeReader:
    def __init__(self, invoices):
        self.calls = []
        self.missing_reads = False
        self.records = {
            "account.invoice": invoices,
            "account.journal": [
                {"id": 7, "som_sync_odoo_invoices": True},
                {"id": 8, "som_sync_odoo_invoices": False},
            ],
        }

    def execute(self, model, method, *args):
        self.calls.append((model, method, args))
        if model not in self.records or method not in {"search", "read"}:
            raise AssertionError("Consulta fora de la fase 1: {} {}".format(model, method))
        records = self.records[model]
        if method == "search":
            for field, operator, value in args[0]:
                if "." in field:
                    raise AssertionError("Domini relacionat que pot provocar una cerca massiva")

                def matches(row):
                    actual = row[field]
                    if isinstance(actual, (list, tuple)):
                        actual = exporter.relation_id(actual)
                    if operator == "=":
                        return actual == value
                    if operator == "!=":
                        return actual != value
                    if operator == "in":
                        return actual in value
                    raise AssertionError("Operador inesperat: {}".format(operator))

                records = [row for row in records if matches(row)]
            return [row["id"] for row in records]
        if set(args[1]) & {"payment_ids", "move_id", "invoice_fraccionament_ids", "invoice_line"}:
            raise AssertionError("S'estan llegint dependències que corresponen a fases posteriors")
        if self.missing_reads:
            return []
        return [dict((field, row[field]) for field in args[1] + ["id"])
                for row in records if row["id"] in args[0]]


class OpeningIdentificationTest(unittest.TestCase):
    def test_scopes_company_journals_open_state_and_nonzero_residual(self):
        disabled = invoice(5)
        disabled["journal_id"] = [8, "No habilitat"]
        other_company = invoice(6)
        other_company["company_id"] = [2, "Altra empresa"]
        rows = [invoice(1), invoice(2, -25, invoice_type="out_refund"),
                invoice(3, invoice_type="in_invoice"), invoice(4, invoice_type="in_refund"),
                disabled, other_company, invoice(7, state="paid"), invoice(8, 0),
                invoice(9, state="draft"), invoice(10, state="cancel")]
        for scope, expected in [("customers", [1, 2]), ("suppliers", [3, 4]),
                                ("all", [1, 2, 3, 4])]:
            with self.subTest(scope=scope):
                reader = FakeReader(rows)
                data = exporter.Extractor(reader, 1, invoice_scope=scope).extract("2026-10-14")
                self.assertEqual([item["id"] for item in data["invoices"]], expected)
                journal_searches = [args for model, method, args in reader.calls
                                    if model == "account.journal" and method == "search"]
                self.assertEqual(len(journal_searches), 1)

    def test_reads_only_invoice_headers_in_batches_and_defers_installments(self):
        reader = FakeReader([invoice(1), invoice(2), invoice(3), invoice(4, 0, state="paid")])
        data = exporter.Extractor(reader, 1, batch_size=2).extract("2026-10-14")
        reads = [args[0] for model, method, args in reader.calls if method == "read"]
        self.assertEqual(reads, [[1, 2], [3]])
        self.assertEqual([item["id"] for item in data["invoices"]], [1, 2, 3])
        self.assertNotIn("payment_ids", data["invoices"][0])
        self.assertEqual(set(data), {"invoices", "journal_ids", "diagnostics"})

    def test_reference_date_does_not_filter_current_pending(self):
        reader = FakeReader([invoice(1)])
        extractor = exporter.Extractor(reader, 1)
        self.assertEqual(extractor.extract("2026-10-14"), extractor.extract("2026-12-31"))

    def test_no_enabled_journals_skips_invoice_history(self):
        reader = FakeReader([invoice(1)])
        reader.records["account.journal"] = [{"id": 8, "som_sync_odoo_invoices": False}]
        data = exporter.Extractor(reader, 1).extract("2026-10-14")
        self.assertEqual(data["invoices"], [])
        self.assertFalse(any(model == exporter.INVOICE for model, method, args in reader.calls))

    def test_rejects_incomplete_or_duplicate_reads(self):
        reader = FakeReader([invoice(1)])
        reader.missing_reads = True
        with self.assertRaisesRegex(ValueError, "Lectura incompleta"):
            exporter.Extractor(reader, 1).extract("2026-10-14")
        client = Mock()
        client.execute.side_effect = [[7], [1], [invoice(1), invoice(1)]]
        with self.assertRaisesRegex(ValueError, "duplicada"):
            exporter.Extractor(client, 1).extract("2026-10-14")

    def test_revalidates_selection_if_records_change_between_search_and_read(self):
        changed_records = [invoice(1, state="paid"), invoice(1, 0), invoice(1)]
        changed_records[2]["company_id"] = [2, "Altra empresa"]
        for changed in changed_records:
            with self.subTest(record=changed):
                client = Mock()
                client.execute.side_effect = [[7], [1], [changed]]
                with self.assertRaisesRegex(ValueError, "no compleix la selecció"):
                    exporter.Extractor(client, 1).extract("2026-10-14")

    def test_normalizes_search_ids_and_orders_control_rows(self):
        client = Mock()
        client.execute.side_effect = [[7, 7], [2, 1, 2], [invoice(2), invoice(1)]]
        data = exporter.Extractor(client, 1).extract("2026-10-14")
        self.assertEqual([item["id"] for item in data["invoices"]], [1, 2])
        self.assertEqual(data["journal_ids"], [7])

    def test_missing_date_is_diagnostic_not_blocker(self):
        source = invoice(1)
        source["date_invoice"] = False
        data = exporter.Extractor(FakeReader([source]), 1).extract("2026-10-14")
        self.assertEqual(data["diagnostics"], [{"code": "missing_invoice_date", "invoice_id": 1}])
        self.assertEqual(len(data["invoices"]), 1)

    def test_id_manifest_csv_decimal_totals_and_no_overwrite(self):
        data = exporter.Extractor(FakeReader([invoice(2, 0.2), invoice(1, 0.1)]), 1).extract(
            "2026-10-14")
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "snapshot"
            exporter.write_export(output, data, {"company_id": 1})
            raw = (output / "invoice_ids.json").read_bytes()
            payload = json.loads(raw)
            self.assertEqual(payload["invoice_ids"], [1, 2])
            self.assertEqual(payload["metadata"]["model"], "account.invoice")
            self.assertEqual(payload["metadata"]["phase"], "identify_invoice_ids")
            self.assertEqual(payload["metadata"]["invoice_count"], 2)
            self.assertEqual(payload["control_totals"][0]["residual"], "0.3")
            self.assertNotIn("invoices", payload)
            self.assertEqual({path.name for path in output.iterdir()},
                             {"invoice_ids.json", "invoices.csv"})
            with (output / "invoices.csv").open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream, delimiter=";"))
            self.assertEqual([row["erp_invoice_id"] for row in rows], ["1", "2"])
            self.assertEqual(rows[0]["number"], "F;1\nCatalà")
            with self.assertRaises(OSError) as caught:
                exporter.write_export(output, data, {})
            self.assertEqual(caught.exception.errno, errno.EEXIST)
            self.assertEqual((output / "invoice_ids.json").read_bytes(), raw)

    def test_empty_export_keeps_full_csv_header(self):
        data = exporter.Extractor(FakeReader([]), 1).extract("2026-10-14")
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "snapshot"
            exporter.write_export(output, data, {})
            payload = json.loads((output / "invoice_ids.json").read_text())
            self.assertEqual(payload["invoice_ids"], [])
            self.assertEqual(payload["control_totals"], [])
            with (output / "invoices.csv").open(encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream, delimiter=";")
                self.assertEqual(reader.fieldnames, exporter.CSV_FIELDS)
                self.assertEqual(list(reader), [])

    def test_control_totals_do_not_mix_types_or_currencies(self):
        rows = [invoice(1, 10), invoice(2, 20, invoice_type="out_refund"), invoice(3, 30)]
        rows[2]["currency_id"] = [5, "USD"]
        data = exporter.Extractor(FakeReader(rows), 1).extract("2026-10-14")
        totals = exporter.control_totals(exporter.invoice_rows(data))
        self.assertEqual(len(totals), 3)
        self.assertEqual(sum(item["invoice_count"] for item in totals), 3)

    def test_main_uses_erppeek_dbconfig_and_writes_phase_one_metadata(self):
        config = {"server": "http://erp-proves:8069", "db": "erp_copia_assaig",
                  "user": "proves", "password": "contrasenya-de-prova"}
        factory = Mock(return_value=FakeReader([invoice(1)]))
        modules = {"dbconfig": SimpleNamespace(erppeek=config),
                   "erppeek": SimpleNamespace(Client=factory)}
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "snapshot"
            with patch.dict(sys.modules, modules), patch("builtins.print"), \
                    patch.object(exporter.logging, "basicConfig"):
                result = exporter.main([
                    "--cutoff", "2026-10-14", "--company-id", "1",
                    "--invoice-scope", "customers", "--snapshot-reference", "copia-proves",
                    "--output", str(output),
                ])
            self.assertEqual(result, 0)
            factory.assert_called_once_with(**config)
            payload = json.loads((output / "invoice_ids.json").read_text())
            metadata = payload["metadata"]
            self.assertEqual(metadata["source_database"], config["db"])
            self.assertEqual(metadata["reference_date"], metadata["cutoff"])
            self.assertEqual(metadata["residual_basis"], "current_erp_state")
            self.assertEqual(metadata["invoice_scope"], "customers")
            self.assertTrue(metadata["selection"]["only_sync_enabled_journals"])
            self.assertNotIn(config["password"], json.dumps(payload))

    def test_cutoff_alias_and_all_scope_default_are_preserved(self):
        with tempfile.TemporaryDirectory() as parent:
            common = ["--company-id", "1", "--snapshot-reference", "copia",
                      "--output", str(Path(parent) / "snapshot")]
            current = exporter.parse_args(["--reference-date", "2026-10-14"] + common)
            legacy = exporter.parse_args(["--cutoff", "2026-10-14"] + common)
            self.assertEqual(current, legacy)
            self.assertEqual(current.invoice_scope, "all")

    def test_rejects_invalid_amounts(self):
        for value in (False, None, "incorrecte", float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                exporter.amount(value)


if __name__ == "__main__":
    unittest.main()
