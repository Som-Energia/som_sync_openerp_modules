# -*- coding: utf-8 -*-
"""Saldos natius i progrés per lots, sense connexió a l'ERP."""

from __future__ import print_function, unicode_literals

import os
import sys
import unittest
from datetime import date

from opening_test_support import (
    Mock, Namespace, SCRIPTS, StringIO, TestCase, patch, read_bytes, read_csv,
    redirect_stderr, redirect_stdout, temporary_directory, write_text,
)

with patch.object(sys, "path", [SCRIPTS] + sys.path):
    import export_account_balances_csv as exporter


def fiscalyear(record_id=10, company=1, start="2026-01-01", stop="2026-12-31"):
    return {"id": record_id, "name": "Exercici 2026", "date_start": start, "date_stop": stop,
            "company_id": [company, "Empresa"] if company else False}


def account(record_id, code, company=1, active=True, debit=100.1, credit=25.05, balance=75.05):
    return {"id": record_id, "code": code, "name": 'Compte; "València"\n€',
            "company_id": [company, "Empresa"], "odoo_account_code": "430000001",
            "active": active, "debit": debit, "credit": credit, "balance": balance}


class FakeReader(object):
    def __init__(self, accounts=None, years=None):
        self.records = {
            exporter.ACCOUNT: accounts if accounts is not None else [account(1, "000000000001")],
            exporter.FISCALYEAR: years if years is not None else [fiscalyear()],
        }
        self.calls = []
        self.events = []
        self.bad_read = None
        self.duplicate = False
        self.changed = None

    def execute(self, model, method, *args):
        self.calls.append((model, method, args))
        if model not in self.records or method not in ("search", "read"):
            raise AssertionError("Només es poden llegir exercicis i comptes, no descarregar apunts")
        rows = self.records[model]
        context = args[-1]
        if model == exporter.ACCOUNT and context.get("active_test", True):
            rows = [row for row in rows if row["active"]]
        if method == "search":
            for field, operator, value in args[0]:
                if "." in field:
                    raise AssertionError("Domini relacionat inesperat")

                def matches(row):
                    actual = row[field]
                    if isinstance(actual, list):
                        actual = actual[0]
                    if operator == "=":
                        return actual == value
                    if operator == "<=":
                        return actual <= value
                    if operator == ">=":
                        return actual >= value
                    if operator == "=like":
                        if value != "_" * 12:
                            raise AssertionError("El patró ha de limitar a 12 caràcters")
                        return len(actual) == 12
                    raise AssertionError("Operador inesperat")

                rows = [row for row in rows if matches(row)]
            return [row["id"] for row in rows]
        fields = args[1]
        kind = "fiscalyear" if model == exporter.FISCALYEAR else (
            "balance" if "balance" in fields else "metadata")
        self.events.append((kind, list(args[0])))
        result = [{field: row[field] for field in fields + ["id"]}
                  for row in reversed(rows) if row["id"] in args[0]]
        if kind == "balance" and self.changed:
            result[0].update(self.changed)
        if kind == self.bad_read:
            return result + result[:1] if self.duplicate else []
        return result


class Progress(object):
    def __init__(self, events):
        self.events = events
        self.updates = []
        self.closed = False
        self.options = None

    def __call__(self, **kwargs):
        self.options = kwargs
        return self

    def __enter__(self):
        return self

    def update(self, count):
        self.updates.append(count)
        self.events.append(("progress", count))

    def __exit__(self, *args):
        self.closed = True
        return False


class AccountBalancesTest(TestCase):
    def extract(self, reader=None, batch_size=2):
        reader = reader or FakeReader()
        progress = Progress(reader.events)
        rows = exporter.Extractor(reader, 1, "2026-10-19", batch_size).extract(progress)
        return rows, progress

    def test_exact_codes_company_inactive_zero_and_native_balance_are_preserved(self):
        zero = account(1, "000000000001", active=False, debit=0, credit=0, balance=0)
        native = account(2, "430000000002", debit=10, credit=2, balance=7)
        native["odoo_account_code"] = False
        reader = FakeReader([native, zero, account(3, "572000000003", company=2),
                             account(4, "12345678901"), account(5, "1234567890123"),
                             account(6, "43000000000X"), account(7, "１２３４５６７８９０１２")])
        rows, progress = self.extract(reader)
        self.assertEqual([row["account_id"] for row in rows], [1, 2])
        self.assertEqual(rows[0]["code"], "000000000001")
        self.assertEqual(rows[0]["balance"], "0")
        self.assertEqual(rows[1]["balance"], "7")  # Valor natiu, no recalculat com 10 - 2.
        self.assertEqual(rows[1]["odoo_account_code"], "")
        self.assertEqual(progress.options["total"], 2)
        self.assertIs(progress.options["file"], sys.stderr)
        self.assertEqual(progress.updates, [2])

    def test_context_is_current_fiscalyear_bydate_and_keeps_special_periods(self):
        reader = FakeReader(years=[fiscalyear(9, start="2025-01-01", stop="2025-12-31"),
                                   fiscalyear(), fiscalyear(20, company=2),
                                   fiscalyear(30, company=0)])
        rows, _ = self.extract(reader)
        balance_reads = [args for model, method, args in reader.calls
                         if method == "read" and "balance" in args[1]]
        self.assertEqual(balance_reads[0][-1], {
            "active_test": False, "fiscalyear": 10, "date_from": "2026-01-01",
            "date_to": "2026-10-19", "state": "bydate",
        })
        self.assertEqual(rows[0]["fiscalyear_id"], 10)
        self.assertEqual(rows[0]["date_to"], "2026-10-19")
        self.assertEqual(len([call for call in reader.calls if call[0] == exporter.FISCALYEAR
                              and call[1] == "search"]), 1)

    def test_fiscalyear_start_is_not_assumed_to_be_january(self):
        reader = FakeReader(years=[fiscalyear(start="2026-04-01", stop="2027-03-31")])
        self.extract(reader)
        context = next(args[-1] for model, method, args in reader.calls
                       if method == "read" and "balance" in args[1])
        self.assertEqual(context["date_from"], "2026-04-01")

    def test_shared_fiscalyear_is_used_only_when_no_company_specific_year_exists(self):
        rows, _ = self.extract(FakeReader(years=[fiscalyear(30, company=0)]))
        self.assertEqual(rows[0]["fiscalyear_id"], 30)
        for years in ([], [fiscalyear(), fiscalyear(11)],
                      [fiscalyear(30, company=0), fiscalyear(31, company=0)]):
            reader = FakeReader(years=years)
            with self.assertRaisesRegex(ValueError, "Cal un únic exercici"):
                self.extract(reader)
            self.assertFalse(any(model == exporter.ACCOUNT for model, _, _ in reader.calls))

    def test_progress_advances_after_validated_batches_and_uses_selected_total(self):
        reader = FakeReader([account(index, "%012d" % index) for index in range(1, 6)]
                            + [account(6, "43000000000X")])
        rows, progress = self.extract(reader, batch_size=2)
        self.assertEqual(progress.options["total"], 5)
        self.assertEqual(progress.updates, [2, 2, 1])
        self.assertTrue(progress.closed)
        self.assertEqual(len(rows), 5)
        events = [event for event in reader.events if event[0] in ("balance", "progress")]
        self.assertEqual([kind for kind, value in events],
                         ["balance", "progress", "balance", "progress", "balance", "progress"])
        reads = [args[0] for _, method, args in reader.calls if method == "read"]
        self.assertTrue(all(len(ids) <= 2 for ids in reads))

    def test_incomplete_duplicate_or_invalid_balance_does_not_advance_progress(self):
        for duplicate in (False, True):
            reader = FakeReader()
            reader.bad_read, reader.duplicate = "balance", duplicate
            progress = Progress(reader.events)
            with self.assertRaisesRegex(ValueError, "incompleta o duplicada"):
                exporter.Extractor(reader, 1, "2026-10-19").extract(progress)
            self.assertEqual(progress.updates, [])
            self.assertTrue(progress.closed)
        for value in (False, None, "incorrecte", float("nan"), float("inf")):
            reader = FakeReader([account(1, "000000000001", balance=value)])
            progress = Progress(reader.events)
            with self.assertRaises(ValueError):
                exporter.Extractor(reader, 1, "2026-10-19").extract(progress)
            self.assertEqual(progress.updates, [])
            self.assertTrue(progress.closed)

    def test_metadata_and_fiscalyear_reads_must_be_complete(self):
        for kind in ("metadata", "fiscalyear"):
            reader = FakeReader()
            reader.bad_read = kind
            with self.assertRaisesRegex(ValueError, "incompleta o duplicada"):
                self.extract(reader)

    def test_changed_account_company_or_code_is_rejected_before_progress(self):
        for changed in ({"company_id": [2, "Altra empresa"]}, {"code": "000000000002"}):
            reader = FakeReader()
            reader.changed = changed
            progress = Progress(reader.events)
            with self.assertRaisesRegex(ValueError, "ha canviat"):
                exporter.Extractor(reader, 1, "2026-10-19").extract(progress)
            self.assertEqual(progress.updates, [])

    def run_main(self, reader, output):
        config = {"server": "http://erp-proves:8069", "db": "copia-proves",
                  "user": "proves", "password": "secret-proves"}
        factory = Mock(return_value=reader)
        progress = Progress(reader.events)
        modules = {"dbconfig": Namespace(erppeek=config), "erppeek": Namespace(Client=factory),
                   "tqdm": Namespace(tqdm=progress)}
        stdout, stderr = StringIO(), StringIO()
        with patch.dict(sys.modules, modules), redirect_stdout(stdout), redirect_stderr(stderr), \
                patch.object(exporter, "date", Namespace(today=lambda: date(2026, 10, 19))), \
                patch.object(exporter.logging, "basicConfig"):
            result = exporter.main(["--company-id", "1", "--output", output])
        factory.assert_called_once_with(**config)
        return result, stdout.getvalue(), stderr.getvalue(), progress

    def test_main_writes_utf8_csv_summary_and_today_without_live_dependencies(self):
        zero = account(1, "000000000001", debit=0, credit=0, balance=0)
        zero["odoo_account_code"] = False
        with temporary_directory() as parent:
            output = os.path.join(parent, "saldos-à.csv")
            result, stdout, stderr, _ = self.run_main(FakeReader([zero]), output)
            self.assertEqual(result, 0)
            fields, rows = read_csv(output)
            self.assertEqual(fields, exporter.CSV_FIELDS)
            self.assertEqual(rows[0]["code"], "000000000001")
            self.assertEqual(rows[0]["name"], 'Compte; "València"\n€')
            self.assertEqual(rows[0]["date_to"], "2026-10-19")
            self.assertEqual(rows[0]["odoo_account_code"], "")
            self.assertIn("1 comptes; 1 amb saldo zero; 1 sense codi Odoo", stdout)
            self.assertNotIn("secret-proves", stdout + stderr + read_bytes(output).decode("utf-8"))

    def test_empty_export_has_full_header_and_zero_progress_total(self):
        with temporary_directory() as parent:
            output = os.path.join(parent, "empty.csv")
            result, stdout, _, progress = self.run_main(FakeReader(accounts=[]), output)
            self.assertEqual(result, 0)
            self.assertEqual(read_csv(output), (exporter.CSV_FIELDS, []))
            self.assertEqual(progress.options["total"], 0)
            self.assertEqual(progress.updates, [])
            self.assertTrue(progress.closed)
            self.assertIn("0 comptes", stdout)

    def test_failed_extraction_does_not_create_csv(self):
        with temporary_directory() as parent:
            output = os.path.join(parent, "failed.csv")
            reader = FakeReader()
            reader.bad_read = "balance"
            result, _, stderr, _ = self.run_main(reader, output)
            self.assertEqual(result, 1)
            self.assertFalse(os.path.exists(output))
            self.assertIn("No s'ha pogut completar l'exportació de saldos", stderr)

    def test_invalid_arguments_and_existing_output_are_rejected(self):
        with temporary_directory() as parent:
            output = os.path.join(parent, "existing.csv")
            write_text(output, "dades existents")
            for args in (["--company-id", "1", "--output", output],
                         ["--company-id", "0", "--output", os.path.join(parent, "new.csv")],
                         ["--company-id", "1", "--batch-size", "0",
                          "--output", os.path.join(parent, "new.csv")]):
                with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as caught:
                    exporter.parse_args(args)
                self.assertEqual(caught.exception.code, 2)
            self.assertEqual(read_bytes(output), b"dades existents")


if __name__ == "__main__":
    unittest.main()
