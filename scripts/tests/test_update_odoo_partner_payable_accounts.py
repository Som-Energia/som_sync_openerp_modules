from __future__ import unicode_literals

from contextlib import contextmanager
import copy
import csv
import io
import os
import shutil
import sys
import tempfile
import unittest


SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "update_odoo_partner_payable_accounts.py")
if sys.version_info[0] == 2:
    import imp
    from httplib import IncompleteRead
    updater = imp.load_source("payable_updater", SCRIPT)
else:
    import importlib.util
    from http.client import IncompleteRead
    SPEC = importlib.util.spec_from_file_location("payable_updater", SCRIPT)
    updater = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(updater)


@contextmanager
def temporary_directory():
    directory = tempfile.mkdtemp()
    try:
        yield directory
    finally:
        shutil.rmtree(directory)


def read_report(path):
    with io.open(path, encoding="utf-8-sig", newline="") as report:
        lines = (line.encode("utf-8") for line in report) if updater.PY2 else report
        rows = list(csv.DictReader(lines))
    if updater.PY2:
        return [{key: value.decode("utf-8") for key, value in row.items()} for row in rows]
    return rows


class TestCase(unittest.TestCase):
    if not hasattr(unittest.TestCase, "assertRaisesRegex"):
        assertRaisesRegex = unittest.TestCase.assertRaisesRegexp

    if not hasattr(unittest.TestCase, "subTest"):
        @contextmanager
        def subTest(self, **params):
            yield


class FakeOdoo:
    def __init__(self):
        self.accounts = [
            dict(id=10, code="400.000.001", account_type="liability_payable", deprecated=False),
            dict(id=20, code="400000100", account_type="liability_payable", deprecated=False),
            dict(id=30, code="400000200", account_type="liability_payable", deprecated=False),
        ]
        self.partners = [self.partner(1, 10, [2]), self.partner(2, 10, [], commercial=1)]
        self.writes = []

    @staticmethod
    def partner(pid, account, children, commercial=None):
        return dict(id=pid, name="Partner {}".format(pid), child_ids=children,
                    is_company=commercial is None,
                    commercial_partner_id=[commercial or pid, "Commercial"],
                    property_account_payable_id=[account, "Account"])

    def __call__(self, model, method, args, kwargs):
        assert kwargs["context"] == {"allowed_company_ids": [1], "active_test": False}
        if model == "res.company":
            return [dict(id=1, name="Company")]
        if model == "account.account":
            if method == "search_read":
                codes = args[0][0][2]
                return copy.deepcopy([a for a in self.accounts if a["code"] in codes])
            return copy.deepcopy([a for a in self.accounts if a["id"] in args[0]])
        if method == "search_read":
            assert ("is_company", "=", True) in args[0]
            assert kwargs["fields"] == ["name", updater.FIELD]
            _, operator, value = args[0][0]
            matches = [p for p in self.partners if (
                p["id"] > value if operator == ">" else p["id"] in value)]
            if ("is_company", "=", True) in args[0]:
                matches = [p for p in matches if p["is_company"]]
            return copy.deepcopy(sorted(
                matches,
                key=lambda p: p["id"])[:kwargs["limit"]])
        if method == "read":
            assert all(p["is_company"] for p in self.partners if p["id"] in args[0])
            return copy.deepcopy([p for p in self.partners if p["id"] in args[0]])
        if method == "write":
            self.writes.append(copy.deepcopy(args))
            by_id = {p["id"]: p for p in self.partners}

            def apply(pid):
                partner = by_id[pid]
                partner[updater.FIELD] = [args[1][updater.FIELD], "New account"]
                for child in partner["child_ids"]:
                    if not by_id[child]["is_company"]:
                        apply(child)

            for pid in args[0]:
                apply(pid)
            return True
        raise AssertionError((model, method))


class PaginationTests(TestCase):
    def test_read_limit_bounds_requests_and_stops_without_extra_page(self):
        for limit, expected_sizes in ((10, [10]), (200, [200]), (205, [200, 5])):
            with self.subTest(limit=limit):
                odoo = FakeOdoo()
                odoo.partners = [odoo.partner(pid, 10, []) for pid in range(1, 501)]
                requests = []

                def call(model, method, args, kwargs):
                    requests.append(kwargs["limit"])
                    return odoo(model, method, args, kwargs)

                partners = updater.read_partners(
                    call, 1, {"allowed_company_ids": [1], "active_test": False}, limit=limit)
                self.assertEqual(requests, expected_sizes)
                self.assertEqual([p["id"] for p in partners], list(range(1, limit + 1)))

    def test_multiple_pages_with_gaps_do_not_omit_or_duplicate_partners(self):
        odoo = FakeOdoo()
        odoo.partners = [odoo.partner(pid, 10, []) for pid in range(3, 1218, 3)]
        pages = []

        def call(model, method, args, kwargs):
            self.assertEqual(args[0][1:], [("is_company", "=", True),
                                           "|", ("company_id", "=", 1), ("company_id", "=", False)])
            self.assertEqual(kwargs["order"], "id")
            self.assertEqual(kwargs["limit"], 200)
            page = odoo(model, method, args, kwargs)
            pages.append(len(page))
            return page

        partners = updater.read_partners(
            call, 1, {"allowed_company_ids": [1], "active_test": False})
        self.assertEqual(partners, odoo.partners)
        self.assertEqual(pages, [200, 200, 5, 0])
        self.assertEqual(odoo.writes, [])

    def test_interrupted_page_stops_planning_before_any_writes(self):
        odoo = FakeOdoo()

        def call(model, method, args, kwargs):
            if model == "res.partner" and method == "search_read" and args[0][0][2] > 0:
                raise IncompleteRead(b"partial response")
            return odoo(model, method, args, kwargs)

        with self.assertRaisesRegex(RuntimeError, "after ID 1.*No partner updates have started"):
            updater.prepare_plan(call, {"400.000.001": "400000100"}, 1)
        self.assertEqual(odoo.writes, [])

    def test_empty_partner_result(self):
        odoo = FakeOdoo()
        odoo.partners = []
        self.assertEqual(updater.read_partners(
            odoo, 1, {"allowed_company_ids": [1], "active_test": False}), [])


class MappingTests(TestCase):
    def mapping_file(self, directory, text):
        path = os.path.join(directory, "mapping.csv")
        with io.open(path, "w", encoding="utf-8", newline="") as output:
            output.write(text)
        return path

    def test_bom_leading_zeros_dots_and_destination_only(self):
        with temporary_directory() as directory:
            path = self.mapping_file(
                directory, '\ufeffold_code,new_code\n" 040.000.001 ",040.000.100\n'
                ',400000200\n\n,\n')
            self.assertEqual(updater.read_mappings(path), {"040000001": "040000100"})

    def test_conflicts_show_both_rows(self):
        with temporary_directory() as directory:
            path = self.mapping_file(
                directory, 'old_code,new_code\n400.000.001,400.000.100\n400000001,400000200\n')
            with self.assertRaisesRegex(ValueError, "row 2 -> 400000100, row 3 -> 400000200"):
                updater.read_mappings(path)

    def test_incomplete_source_rejected(self):
        with temporary_directory() as directory:
            path = self.mapping_file(directory, 'old_code,new_code\n400.000.001,\n')
            with self.assertRaisesRegex(ValueError, "has no destination"):
                updater.read_mappings(path)

    def test_malformed_columns_rejected(self):
        for row in ('400.000.001', '400.000.001,400000100,extra'):
            with self.subTest(row=row), temporary_directory() as directory:
                path = self.mapping_file(directory, 'old_code,new_code\n' + row + '\n')
                with self.assertRaisesRegex(ValueError, "exactly two columns"):
                    updater.read_mappings(path)

    def test_wrong_header_or_delimiter_rejected(self):
        for header in ('old_code;new_code', 'source,destination'):
            with self.subTest(header=header), temporary_directory() as directory:
                path = self.mapping_file(directory, header + '\n')
                with self.assertRaisesRegex(ValueError, "CSV header must be"):
                    updater.read_mappings(path)

    def test_identical_duplicates_accepted(self):
        with temporary_directory() as directory:
            path = self.mapping_file(
                directory, 'old_code,new_code\n400.000.001,400.000.100\n400000001,400000100\n')
            self.assertEqual(updater.read_mappings(path), {"400000001": "400000100"})

    def test_empty_mapping_rejected(self):
        with temporary_directory() as directory:
            path = self.mapping_file(directory, 'old_code,new_code\n\n,\n')
            with self.assertRaisesRegex(ValueError, "CSV contains no mappings"):
                updater.read_mappings(path)


class UpdateTests(TestCase):
    def test_utf8_company_and_partner_names_survive_report_output(self):
        odoo = FakeOdoo()
        odoo.partners[0]["name"] = "Prove\u00efdors d\u2019energia \u2014 Val\u00e8ncia"

        def call(model, method, args, kwargs):
            records = odoo(model, method, args, kwargs)
            if model == "res.company":
                records[0]["name"] = "Cooperativa d\u2019energia"
            return records

        rows, context = updater.prepare_plan(call, {"400.000.001": "400000100"}, 1)
        with temporary_directory() as directory:
            path = os.path.join(directory, "informe_\u00e8.csv")
            updater.execute_plan(odoo, rows, context, path, dry_run=True)
            self.assertEqual(read_report(path)[0]["partner_name"], odoo.partners[0]["name"])

    def test_existing_report_is_not_overwritten(self):
        odoo = FakeOdoo()
        rows, context = updater.prepare_plan(odoo, {"400.000.001": "400000100"}, 1)
        with temporary_directory() as directory:
            path = os.path.join(directory, "report.csv")
            with io.open(path, "w", encoding="utf-8") as report:
                report.write("existing report")
            with self.assertRaises((IOError, OSError)):
                updater.execute_plan(odoo, rows, context, path)
            with io.open(path, encoding="utf-8") as report:
                self.assertEqual(report.read(), "existing report")
        self.assertEqual(odoo.writes, [])

    def test_read_limit_counts_unchanged_and_skipped_companies(self):
        odoo = FakeOdoo()
        odoo.accounts.append(dict(
            id=40, code="400900100", account_type="liability_current", deprecated=False))
        odoo.partners = [
            odoo.partner(5, 10, []), odoo.partner(1, 20, []),
            odoo.partner(4, 10, []), odoo.partner(2, 30, []),
            odoo.partner(3, 10, []),
        ]
        mappings = {"400.000.001": "400000100", "400000100": "400000100",
                    "400000200": "400900100"}
        rows, context = updater.prepare_plan(odoo, mappings, 1, limit=3)
        self.assertEqual([r["partner_id"] for r in rows if r["status"] == "planned"], [3])
        self.assertEqual([r["partner_id"]
                         for r in rows if r["status"] == "skipped_destination"], [2])
        with temporary_directory() as directory:
            preview = os.path.join(directory, "preview.csv")
            updater.execute_plan(odoo, rows, context, preview, dry_run=True)
            self.assertEqual(odoo.writes, [])
            self.assertEqual([r["partner_id"] for r in read_report(preview)
                              if r["status"] == "would_update"], ["3"])
            updater.execute_plan(odoo, rows, context, os.path.join(directory, "applied.csv"))
        self.assertEqual(odoo.writes, [[[3], {updater.FIELD: 20}]])
        self.assertEqual(odoo.partners[0][updater.FIELD][0], 10)

    def test_limit_above_available_changes_does_not_add_updates(self):
        odoo = FakeOdoo()
        rows, _ = updater.prepare_plan(odoo, {"400.000.001": "400000100"}, 1, limit=10)
        self.assertEqual([r["partner_id"] for r in rows], [1])

    def test_nonpositive_limits_rejected_before_rpc(self):
        for limit in (0, -1):
            with self.subTest(limit=limit):
                def call(*args):
                    self.fail("Invalid limit must not call Odoo")

                with self.assertRaisesRegex(ValueError, "positive integer"):
                    updater.prepare_plan(call, {"400.000.001": "400000100"}, 1, limit=limit)

    def test_unlinked_person_is_not_read_or_updated(self):
        odoo = FakeOdoo()
        odoo.partners.append(odoo.partner(3, 10, [], commercial=3))
        rows, context = updater.prepare_plan(odoo, {"400.000.001": "400000100"}, 1)
        self.assertEqual([r["partner_id"] for r in rows], [1])
        with temporary_directory() as directory:
            updater.execute_plan(odoo, rows, context, os.path.join(directory, "report.csv"))
        self.assertEqual(odoo.writes, [[[1], {updater.FIELD: 20}]])
        self.assertEqual(odoo.partners[2][updater.FIELD][0], 10)

    def test_linked_contact_is_not_an_independent_update_candidate(self):
        odoo = FakeOdoo()
        odoo.partners[0][updater.FIELD] = [20, "Already correct"]
        rows, _ = updater.prepare_plan(odoo, {"400.000.001": "400000100"}, 1)
        self.assertEqual(rows, [])
        self.assertEqual(odoo.writes, [])

    def test_nested_linked_contacts_are_left_to_odoo_propagation(self):
        odoo = FakeOdoo()
        odoo.partners[1]["child_ids"] = [3]
        odoo.partners.append(odoo.partner(3, 10, [], commercial=1))
        rows, context = updater.prepare_plan(odoo, {"400.000.001": "400000100"}, 1)
        self.assertEqual([r["partner_id"] for r in rows], [1])
        with temporary_directory() as directory:
            updater.execute_plan(odoo, rows, context, os.path.join(directory, "report.csv"))
        self.assertEqual(odoo.writes, [[[1], {updater.FIELD: 20}]])
        self.assertEqual([p[updater.FIELD][0] for p in odoo.partners], [20, 20, 20])

    def test_dry_run_reports_only_companies_without_writing(self):
        odoo = FakeOdoo()
        rows, context = updater.prepare_plan(odoo, {"400.000.001": "400000100"}, 1)
        self.assertEqual([r["owner"] for r in rows], [1])
        with temporary_directory() as directory:
            path = os.path.join(directory, "report.csv")
            updater.execute_plan(odoo, rows, context, path, dry_run=True)
            records = read_report(path)
            self.assertEqual([r["status"] for r in records], ["would_update"])
            self.assertEqual([r["partner_id"] for r in records], ["1"])
        self.assertEqual(odoo.writes, [])

    def test_write_company_once_and_let_odoo_sync_children(self):
        odoo = FakeOdoo()
        rows, context = updater.prepare_plan(odoo, {"400.000.001": "400000100"}, 1)
        with temporary_directory() as directory:
            updater.execute_plan(odoo, rows, context, os.path.join(directory, "report.csv"))
        self.assertEqual(odoo.writes, [[[1], {updater.FIELD: 20}]])
        self.assertEqual([p[updater.FIELD][0] for p in odoo.partners], [20, 20])

    def test_snapshot_prevents_chain_remapping(self):
        odoo = FakeOdoo()
        odoo.partners = [odoo.partner(1, 10, []), odoo.partner(2, 20, [])]
        rows, context = updater.prepare_plan(odoo, {
            "400.000.001": "400000100", "400000100": "400000200"}, 1)
        with temporary_directory() as directory:
            updater.execute_plan(odoo, rows, context, os.path.join(directory, "report.csv"))
        self.assertEqual([p[updater.FIELD][0] for p in odoo.partners], [20, 30])

    def test_conflicting_contact_mapping_does_not_block_company_update(self):
        odoo = FakeOdoo()
        odoo.partners[1][updater.FIELD] = [30, "Other account"]
        rows, context = updater.prepare_plan(odoo, {
            "400.000.001": "400000100", "400000200": "400000200"}, 1)
        self.assertEqual([r["partner_id"] for r in rows], [1])
        with temporary_directory() as directory:
            updater.execute_plan(odoo, rows, context, os.path.join(directory, "report.csv"))
        self.assertEqual(odoo.writes, [[[1], {updater.FIELD: 20}]])

    def test_invalid_destination_fails_before_writes(self):
        odoo = FakeOdoo()
        odoo.accounts[1]["account_type"] = "asset_receivable"
        with self.assertRaisesRegex(ValueError, "non-deprecated payable"):
            updater.prepare_plan(odoo, {"400.000.001": "400000100"}, 1)
        self.assertEqual(odoo.writes, [])

    def test_excluded_destinations_reported_without_writes_to_affected_partners(self):
        for code in ("400900100", "400900200", "400900800"):
            for dry_run in (True, False):
                with self.subTest(code=code, dry_run=dry_run):
                    odoo = FakeOdoo()
                    odoo.accounts.append(dict(
                        id=40, code=code, account_type="liability_current", deprecated=False))
                    odoo.partners = [odoo.partner(1, 10, []), odoo.partner(2, 20, [])]
                    rows, context = updater.prepare_plan(odoo, {
                        "400.000.001": code, "400000100": "400000200"}, 1)
                    self.assertEqual(rows[0]["status"], "skipped_destination")
                    self.assertEqual(rows[1]["status"], "planned")
                    with temporary_directory() as directory:
                        path = os.path.join(directory, "report.csv")
                        updater.execute_plan(odoo, rows, context, path, dry_run=dry_run)
                        skipped = [r for r in read_report(path)
                                   if r["status"] == "skipped_destination"]
                        self.assertEqual(len(skipped), 1)
                        self.assertEqual(skipped[0]["new_code"], code)
                    self.assertEqual(odoo.partners[0][updater.FIELD][0], 10)
                    self.assertEqual(odoo.writes, [] if dry_run else [[[2], {updater.FIELD: 30}]])

    def test_child_mapping_to_excluded_destination_is_not_used(self):
        odoo = FakeOdoo()
        odoo.accounts.append(dict(
            id=40, code="400900100", account_type="liability_current", deprecated=False))
        odoo.partners[1][updater.FIELD] = [30, "Other account"]
        odoo.partners.append(odoo.partner(3, 20, []))
        rows, context = updater.prepare_plan(odoo, {
            "400.000.001": "400000100", "400000200": "400900100",
            "400000100": "400.000.001"}, 1)
        self.assertEqual([r["status"] for r in rows],
                         ["planned", "planned"])
        self.assertEqual([r["partner_id"] for r in rows], [1, 3])
        with temporary_directory() as directory:
            updater.execute_plan(odoo, rows, context, os.path.join(directory, "report.csv"))
        self.assertEqual(sorted(odoo.writes, key=lambda write: write[0]),
                         [[[1], {updater.FIELD: 20}], [[3], {updater.FIELD: 10}]])
        self.assertEqual([p[updater.FIELD][0] for p in odoo.partners], [20, 20, 10])

    def test_inaccessible_child_does_not_block_planning(self):
        odoo = FakeOdoo()
        odoo.partners.pop()
        rows, _ = updater.prepare_plan(odoo, {"400.000.001": "400000100"}, 1)
        self.assertEqual([r["partner_id"] for r in rows], [1])
        self.assertEqual(odoo.writes, [])

    def test_concurrent_change_prevents_write(self):
        odoo = FakeOdoo()
        rows, context = updater.prepare_plan(odoo, {"400.000.001": "400000100"}, 1)
        odoo.partners[0][updater.FIELD] = [30, "Changed concurrently"]
        with temporary_directory() as directory:
            path = os.path.join(directory, "report.csv")
            with self.assertRaisesRegex(RuntimeError, "expected account 10, got 30"):
                updater.execute_plan(odoo, rows, context, path)
            statuses = [r["status"] for r in read_report(path)]
            self.assertEqual(statuses, ["planned", "not_written_precheck_failed"])
        self.assertEqual(odoo.writes, [])


if __name__ == "__main__":
    unittest.main()
