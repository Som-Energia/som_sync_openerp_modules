# -*- coding: utf-8 -*-
"""Proves de selecció i traçabilitat de fraccionaments, sense ERP."""

from __future__ import print_function, unicode_literals

import json
import os
import sqlite3
import sys
import unittest
from opening_test_support import (
    Mock, Namespace, SCRIPTS, StringIO, TestCase, patch, read_bytes, read_csv,
    read_text, redirect_stdout, temporary_directory,
)

with patch.object(sys, "path", [SCRIPTS] + sys.path):
    import opening_03_export_fraccionaments as exporter


def invoice(record_id, invoice_type="out_invoice", state="paid", residual=0, journal=7, company=1):
    return {"id": record_id, "number": "F{}".format(record_id), "type": invoice_type,
            "state": state, "company_id": [company, "Empresa"], "partner_id": [2, "Tercer"],
            "currency_id": [1, "EUR"], "journal_id": [journal, "Diari"],
            "date_invoice": "2026-10-01", "date_due": False, "amount_total": 100,
            "residual": residual}


def agreement(record_id, invoice_id, state="no_cobrat", company=1):
    return {"id": record_id, "invoice_id": [invoice_id, "Factura"],
            "company_id": [company, "Empresa"], "codi": "A;{}\nCatalà".format(record_id),
            "state": state, "import_a_fraccionar": 100}


def line(record_id, agreement_id, state="no_cobrat", value=25):
    row = {"id": record_id, "invoice_fraccionament_id": [agreement_id, "Acord"],
           "company_id": [1, "Empresa"], "import": value, "state": state,
           "data_venciment": "2026-11-01", "data_aplicacio": False}
    row.update({field: False for field in exporter.LINE_RELATIONS})
    return row


class FakeReader:
    def __init__(self, agreements=None, invoices=None, lines=None):
        self.records = {
            "account.journal": [{"id": 7, "som_sync_odoo_invoices": True},
                                {"id": 8, "som_sync_odoo_invoices": False}],
            "account.invoice": invoices if invoices is not None else [invoice(1)],
            exporter.AGREEMENT: agreements if agreements is not None else [agreement(10, 1)],
            exporter.LINE: lines if lines is not None else [line(100, 10)],
        }
        self.calls = []
        self.bad_model = None
        self.duplicate = False

    def execute(self, model, method, *args):
        self.calls.append((model, method, args))
        if model not in self.records or method not in ("search", "read"):
            raise AssertionError("La fase 3 només pot llegir els quatre models esperats")
        rows = self.records[model]
        if method == "search":
            if model == "account.invoice":
                raise AssertionError("No s'ha de cercar l'històric global de factures")
            for field, operator, expected in args[0]:
                if "." in field:
                    raise AssertionError("Domini relacionat amb risc de cerca massiva")
                if operator == "=":
                    rows = [row for row in rows if (
                        exporter.relation_id(row[field]) if isinstance(row[field], list)
                        else row[field]) == expected]
                elif operator == "in":
                    rows = [row for row in rows if (
                        exporter.relation_id(row[field]) if isinstance(row[field], list)
                        else row[field]) in expected]
                else:
                    raise AssertionError("Operador inesperat")
            return [row["id"] for row in rows]
        rows = [{field: row[field] for field in args[1] + ["id"]}
                for row in rows if row["id"] in args[0]]
        if model == self.bad_model:
            return rows + rows[:1] if self.duplicate else []
        return rows


class OpeningFraccionamentsTest(TestCase):
    def extract(self, reader=None, scope="customers", batch_size=200):
        extractor = exporter.Extractor(reader or FakeReader(), 1, batch_size, scope)
        return extractor.extract("2026-10-15")

    def test_selects_pending_agreements_even_with_paid_or_zero_residual_originals(self):
        reader = FakeReader(
            [agreement(10, 1), agreement(11, 2, "parcialment_cobrat"),
             agreement(12, 3, "cobrat"), agreement(13, 4, "cancelat"),
             agreement(14, 5, "cancel_amb_cobs"), agreement(15, 6, company=2),
             agreement(16, 2), agreement(17, 7)],
            [invoice(1), invoice(2, state="open", residual=0), invoice(3), invoice(4),
             invoice(5), invoice(6, company=2), invoice(7, state="open", residual=20)],
            [line(100, 10), line(101, 11), line(102, 16), line(103, 17)])
        data = self.extract(reader)
        self.assertEqual([row["id"] for row in data["agreements"]], [10, 11, 16, 17])
        self.assertEqual(sorted(data["invoices"]), [1, 2, 7])
        self.assertEqual(data["invoices_outside_phase_one_count"], 2)
        self.assertEqual(data["diagnostics"], [])

    def test_company_journal_and_all_invoice_scopes(self):
        invoices = [invoice(1), invoice(2, "out_refund"), invoice(3, "in_invoice"),
                    invoice(4, "in_refund"), invoice(5, journal=8), invoice(6, company=2)]
        agreements = [agreement(index + 10, index) for index in range(1, 7)]
        for scope, expected in [("customers", [11, 12]), ("suppliers", [13, 14]),
                                ("all", [11, 12, 13, 14])]:
            data = self.extract(FakeReader(agreements, invoices, []), scope)
            self.assertEqual([row["id"] for row in data["agreements"]], expected)

    def test_preserves_every_line_state_and_payment_references(self):
        lines = [line(index, 10, state) for index, state in enumerate(
            ["no_cobrat", "remesat", "cobrat", "cancelat", "dividit"], 100)]
        paid = lines[2]
        paid["data_aplicacio"] = "2026-10-10"
        paid.update({field: [500 + index, "Moviment"]
                     for index, field in enumerate(exporter.LINE_RELATIONS)})
        data = self.extract(FakeReader(lines=lines))
        _, rows = exporter.control_rows(data)
        self.assertEqual([row["state"] for row in rows], [row["state"] for row in lines])
        self.assertEqual(rows[2]["application_date"], "2026-10-10")
        for index, field in enumerate(exporter.LINE_RELATIONS):
            self.assertEqual(rows[2][field], 500 + index)

    def test_reads_in_batches_and_does_not_read_computed_payment_totals(self):
        reader = FakeReader([agreement(10, 1), agreement(11, 1), agreement(12, 2)],
                            [invoice(1), invoice(2)],
                            [line(100, 10), line(101, 11), line(102, 12)])
        self.extract(reader, batch_size=2)
        reads = [(model, args) for model, method, args in reader.calls if method == "read"]
        self.assertTrue(all(len(args[0]) <= 2 for model, args in reads))
        self.assertEqual([args[0] for model, args in reads if model == "account.invoice"], [[1, 2]])
        self.assertTrue(all(not {"import_cobrat", "import_no_cobrat", "payment_ids"} & set(args[1])
                            for model, args in reads))
        self.assertEqual(sum(model == "account.journal" for model, _, _ in reader.calls), 1)

    def test_rejects_incomplete_or_duplicate_reads_for_each_model(self):
        for model in (exporter.AGREEMENT, "account.invoice", exporter.LINE):
            for duplicate in (False, True):
                reader = FakeReader()
                reader.bad_model, reader.duplicate = model, duplicate
                with self.assertRaisesRegex(ValueError, "incompleta o duplicada"):
                    self.extract(reader)

    def test_rejects_missing_invoice_and_changed_parent_or_company(self):
        for field, value in [("invoice_id", False), ("state", "cobrat")]:
            row = agreement(10, 1)
            row[field] = value
            client = Mock()
            client.execute.side_effect = [[7], [10], [row]]
            with self.assertRaises(ValueError):
                self.extract(client)
        for field, value in [("invoice_fraccionament_id", [99, "Altre acord"]),
                             ("company_id", [2, "Altra empresa"])]:
            row = line(100, 10)
            row[field] = value
            client = Mock()
            client.execute.side_effect = [[7], [10], [agreement(10, 1)], [invoice(1)], [100], [row]]
            with self.assertRaisesRegex(ValueError, "ha canviat"):
                self.extract(client)

    def test_invalid_amounts_rejected_and_missing_dates_are_diagnostics(self):
        for value in (False, None, "incorrecte", float("nan"), float("inf")):
            row = line(100, 10, value=value)
            with self.assertRaises(ValueError):
                self.extract(FakeReader(lines=[row]))
        row = line(100, 10, "cobrat")
        row["data_venciment"] = False
        data = self.extract(FakeReader(lines=[row]))
        self.assertIn({"code": "missing_due_date", "line_id": 100}, data["diagnostics"])
        self.assertIn({"code": "paid_without_application_date",
                      "line_id": 100}, data["diagnostics"])

    def test_empty_selection_no_journals_and_agreements_without_lines(self):
        reader = FakeReader()
        reader.records["account.journal"] = []
        data = self.extract(reader)
        self.assertEqual(data["agreements"], [])
        self.assertEqual(len(reader.calls), 1)
        data = self.extract(FakeReader(lines=[]))
        self.assertIn({"code": "agreement_without_lines", "fraccionament_id": 10},
                      data["diagnostics"])

    def test_manifest_csv_totals_and_no_overwrite(self):
        data = self.extract(FakeReader(lines=[line(100, 10, "cobrat", 0.1),
                                              line(101, 10, "cobrat", 0.2)]))
        with temporary_directory() as parent:
            output = os.path.join(parent, "export")
            exporter.write_export(output, data, {"company_id": 1})
            payload = json.loads(read_text(os.path.join(output, "fraccionament_ids.json")))
            self.assertEqual(payload["fraccionament_ids"], [10])
            self.assertEqual(payload["invoice_ids"], [1])
            self.assertEqual(payload["metadata"]["model"], exporter.AGREEMENT)
            self.assertEqual(payload["metadata"]["line_count"], 2)
            self.assertEqual(payload["metadata"]["invoices_outside_phase_one_count"], 1)
            self.assertEqual(payload["control_totals"][0]["amount"], "0.3")
            _, rows = read_csv(os.path.join(output, "fraccionaments.csv"))
            self.assertEqual(rows[0]["codi"], "A;10\nCatalà")
            self.assertEqual(rows[0]["invoice_state"], "paid")
            _, rows = read_csv(os.path.join(output, "fraccionament_lines.csv"))
            self.assertEqual([row["erp_line_id"] for row in rows], ["100", "101"])
            self.assertEqual(rows[0]["application_date"], "")
            original = read_bytes(os.path.join(output, "fraccionament_ids.json"))
            with self.assertRaises(OSError):
                exporter.write_export(output, data, {})
            self.assertEqual(read_bytes(os.path.join(output, "fraccionament_ids.json")), original)

    def test_totals_keep_states_types_and_currencies_separate(self):
        rows = [{"invoice_type": kind, "currency_id": currency, "state": state, "amount": "10"}
                for kind, currency, state in [("out_invoice", 1, "cobrat"),
                                              ("out_invoice", 1, "no_cobrat"),
                                              ("out_refund", 1, "cobrat"),
                                              ("out_invoice", 2, "cobrat")]]
        self.assertEqual(len(exporter.control_totals(rows)), 4)

    def test_empty_export_has_stable_headers(self):
        data = self.extract(FakeReader(agreements=[]))
        self.assertEqual(data["invoices_outside_phase_one_count"], 0)
        with temporary_directory() as parent:
            output = os.path.join(parent, "empty")
            exporter.write_export(output, data, {})
            for filename, fields in [("fraccionaments.csv", exporter.AGREEMENT_CSV_FIELDS),
                                     ("fraccionament_lines.csv", exporter.LINE_CSV_FIELDS)]:
                actual_fields, rows = read_csv(os.path.join(output, filename))
                self.assertEqual(actual_fields, fields)
                self.assertEqual(rows, [])

    def test_main_uses_dbconfig_and_reference_is_metadata_only(self):
        config = {"server": "http://erp-proves:8069", "db": "copia-proves",
                  "user": "proves", "password": "secret-proves"}
        factory = Mock(return_value=FakeReader())
        modules = {"dbconfig": Namespace(erppeek=config),
                   "erppeek": Namespace(Client=factory)}
        with temporary_directory() as parent:
            output = os.path.join(parent, "export")
            with patch.dict(sys.modules, modules), redirect_stdout(StringIO()), \
                    patch.object(exporter.logging, "basicConfig"):
                result = exporter.main(["--cutoff", "2020-01-01", "--company-id", "1",
                                        "--invoice-scope", "customers",
                                        "--snapshot-reference", "copia",
                                        "--output", str(output)])
            self.assertEqual(result, 0)
            factory.assert_called_once_with(**config)
            raw = read_text(os.path.join(output, "fraccionament_ids.json"))
            metadata = json.loads(raw)["metadata"]
            self.assertEqual(metadata["source_database"], config["db"])
            self.assertEqual(metadata["reference_date"], "2020-01-01")
            self.assertIsNone(metadata["selection"]["invoice_state_filter"])
            self.assertNotIn(config["password"], raw)

    def test_sql_matches_selection_and_preserves_all_states_and_empty_agreements(self):
        reader = FakeReader(
            [agreement(10, 1), agreement(11, 2, "parcialment_cobrat"),
             agreement(12, 3), agreement(13, 4, "cobrat"), agreement(14, 5)],
            [invoice(1), invoice(2, "out_refund"), invoice(3, "in_invoice"),
             invoice(4), invoice(5, journal=8)],
            [line(100, 10, "cobrat"), line(101, 10, "no_cobrat"), line(102, 10, "cancelat")])
        data = self.extract(reader)
        with sqlite3.connect(":memory:") as connection:
            for model, records in reader.records.items():
                fields = list(records[0])
                table = model.replace(".", "_")
                definitions = ["{} {}".format(field, "INTEGER" if field == "id"
                                              or field.endswith("_id")
                                              or field == "som_sync_odoo_invoices" else "TEXT")
                               for field in fields]
                connection.execute("CREATE TABLE {} ({})".format(table, ", ".join(definitions)))
                connection.executemany("INSERT INTO {} VALUES ({})".format(
                    table, ", ".join("?" for field in fields)),
                    [[exporter.relation_id(row[field]) if isinstance(row[field], list)
                      else row[field] for field in fields] for row in records])
            # Les consultes de control posteriors no formen part de la selecció.
            sql = read_text(os.path.join(SCRIPTS, "opening_03.sql"))
            query = sql[sql.index("SELECT\n"):].split(";", 1)[0]
            rows = connection.execute(query).fetchall()
        self.assertEqual(sorted({row[0] for row in rows}), [row["id"]
                         for row in data["agreements"]])
        self.assertEqual([row[13] for row in rows], [100, 101, 102, None])


if __name__ == "__main__":
    unittest.main()
