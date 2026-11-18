# -*- coding: utf-8 -*-
"""Tests for the idempotent OpenERP analytic-account importer."""

from __future__ import unicode_literals

import os
import sys

from opening_test_support import SCRIPTS, TestCase, patch, temporary_directory, write_text

with patch.object(sys, "path", [SCRIPTS] + sys.path):
    import import_analytic_accounts as importer


class FakeErpPeekClient(object):
    def __init__(self):
        self.company_id = 40
        self.root_id = False
        self.accounts = {}
        self.mappings = {}
        self.odoo_ids = {"010101": 501}
        self.next_id = 100
        self.calls = []

    def execute(self, model, method, *args, **kwargs):
        self.calls.append((model, method, args, kwargs))
        if model == "res.company" and method == "read":
            ids = args[0]
            return [
                {"id": self.company_id, "name": "OpenERP test company"}
                for company_id in ids if company_id == self.company_id
            ]
        if model == importer.ANALYTIC_ACCOUNT and method == "search":
            domain = args[0]
            if ("parent_id", "=", False) in domain:
                return [self.root_id] if self.root_id else []
            code = next(value for key, operator, value in domain if key == "code")
            return [account_id for account_id, record in self.accounts.items()
                    if record["code"] == code
                    and record["company_id"][0] == self.company_id]
        if model == importer.ANALYTIC_ACCOUNT and method == "read":
            return [self._read_account(account_id, args[1]) for account_id in args[0]]
        if model == importer.ANALYTIC_ACCOUNT and method == "create":
            return self._create_account(args[0])
        if model == importer.SYNC and method == "search":
            domain = args[0]
            account_id = next(value for key, operator, value in domain
                              if key == "res_id")
            return [account_id] if account_id in self.mappings else []
        if model == importer.SYNC and method == "read":
            sync_id = args[0][0]
            return [dict({"id": sync_id}, **self.mappings[sync_id])]
        if model == importer.SYNC and method == "get_analytic_account_odoo_id":
            return self.odoo_ids[args[0]]
        if model == importer.SYNC and method == "syncronize_sync":
            account_id = args[2]
            context = kwargs["context"]
            self.mappings[account_id] = {
                "odoo_id": context["odoo_id"],
                "sync_state": "static",
                "sync_profile": "all_in",
            }
            return context["odoo_id"], account_id
        raise AssertionError("Unexpected ERP call: {}.{}".format(model, method))

    def _create_account(self, values):
        account_id = self.next_id
        self.next_id += 1
        record = dict(values)
        record.update({
            "id": account_id,
            "company_id": [values["company_id"], "OpenERP test company"],
            "parent_id": (
                [values["parent_id"], importer.ROOT_NAME]
                if values.get("parent_id") else False
            ),
        })
        self.accounts[account_id] = record
        if record["code"] == importer.ROOT_CODE:
            self.root_id = account_id
        return account_id

    def _read_account(self, account_id, fields):
        record = self.accounts[account_id]
        return dict((field, record.get(field)) for field in fields)


class ImportAnalyticAccountsTest(TestCase):
    def setUp(self):
        self.client = FakeErpPeekClient()
        self.accounts = [{
            "name": "Vendes",
            "reference": "010101",
            "plan": "Project",
            "company": "Som Energia SCCL Assentaments",
        }]

    def prepare(self):
        return importer.prepare_import(
            self.client, self.accounts, self.client.company_id, 2, 3)

    def test_reads_supplied_csv_without_losing_reference_zeroes(self):
        path = os.path.join(
            os.path.dirname(SCRIPTS),
            "som_sync_openerp",
            "migrations",
            "comptes_analítics.csv",
        )

        accounts = importer.read_accounts(path)

        self.assertEqual(len(accounts), 97)
        self.assertEqual(accounts[0]["reference"], "010101")
        self.assertEqual(accounts[0]["plan"], "Project")
        self.assertEqual(
            accounts[0]["company"], "Som Energia SCCL Assentaments")

    def test_dry_run_preflights_remote_and_local_identities_without_writes(self):
        plan = self.prepare()

        self.assertFalse(plan["root"])
        self.assertFalse(plan["accounts"][0]["local_account"])
        self.assertEqual(plan["accounts"][0]["odoo_id"], 501)
        self.assertFalse(
            [call for call in self.client.calls
             if call[1] in ("create", "syncronize_sync")])

    def test_apply_creates_root_child_and_static_mapping(self):
        plan = self.prepare()

        summary = importer.apply_import(
            self.client, plan, self.client.company_id)

        self.assertEqual(summary["created_accounts"], 1)
        self.assertEqual(summary["reused_accounts"], 0)
        self.assertEqual(summary["created_mappings"], 1)
        child = self.client.accounts[101]
        self.assertEqual(child["parent_id"][0], self.client.root_id)
        self.assertEqual(child["type"], "normal")
        self.assertEqual(child["state"], "open")
        self.assertEqual(self.client.accounts[self.client.root_id]["name"], "Projectes Odoo")
        self.assertEqual(self.client.mappings[101]["odoo_id"], 501)
        self.assertEqual(self.client.mappings[101]["sync_state"], "static")

    def test_reexecution_reuses_local_ids_and_existing_static_mapping(self):
        first_plan = self.prepare()
        importer.apply_import(self.client, first_plan, self.client.company_id)
        account_id = next(
            account_id for account_id, account in self.client.accounts.items()
            if account["code"] == "010101")

        second_plan = self.prepare()
        summary = importer.apply_import(
            self.client, second_plan, self.client.company_id)

        self.assertEqual(summary["created_accounts"], 0)
        self.assertEqual(summary["reused_accounts"], 1)
        self.assertEqual(summary["created_mappings"], 0)
        self.assertEqual(
            [candidate_id for candidate_id, account in self.client.accounts.items()
             if account["code"] == "010101"],
            [account_id],
        )

    def test_existing_mapping_to_another_odoo_id_stops_before_writes(self):
        first_plan = self.prepare()
        importer.apply_import(self.client, first_plan, self.client.company_id)
        self.client.odoo_ids["010101"] = 999
        self.client.calls = []

        with self.assertRaises(ValueError):
            self.prepare()

        self.assertFalse(
            [call for call in self.client.calls
             if call[1] in ("create", "syncronize_sync")])

    def test_csv_rejects_duplicate_references(self):
        contents = ";".join(importer.CSV_HEADERS) + "\n"
        row = ["Name", "010101", "", "Project", "Company", "0", "0", "0"]
        contents += ";".join(row) + "\n" + ";".join(row) + "\n"
        with temporary_directory() as directory:
            path = os.path.join(directory, "accounts.csv")
            write_text(path, contents)

            with self.assertRaises(ValueError):
                importer.read_accounts(path)
