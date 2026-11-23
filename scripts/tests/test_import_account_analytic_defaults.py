# -*- coding: utf-8 -*-
"""Tests for importing account analytic defaults from the mapping CSV."""

from __future__ import print_function, unicode_literals

import os
import sys

from opening_test_support import (
    Mock, SCRIPTS, TestCase, patch, read_csv, temporary_directory,
    write_text,
)

with patch.object(sys, "path", [SCRIPTS] + sys.path):
    import import_account_analytic_defaults as importer


class ImportAccountAnalyticDefaultsTest(TestCase):
    def client(self):
        client = Mock()
        client.AccountAnalyticDefault.search.return_value = []
        return client

    def test_read_mappings_skips_rows_without_a_complete_mapping(self):
        with temporary_directory() as parent:
            source = os.path.join(parent, "mapping.csv")
            write_text(
                source,
                "compte_comptabel;compte_analitic\n"
                "600.000.000.000;010102-Aprovisionament\n"
                ";090902-Carrega impositiva\n"
                "710.000.000.000;\n"
            )

            mappings = importer.read_mappings(source)

        self.assertEqual(
            mappings,
            [("600.000.000.000", "010102-Aprovisionament")],
        )

    def test_resolves_codes_and_creates_defaults_with_sequence_100(self):
        client = self.client()
        client.AccountAccount.search.return_value = [11]
        client.AccountAccount.read.return_value = [
            {"id": 11, "code": "600000000000"}
        ]
        client.AccountAnalyticAccount.search.return_value = [22]
        client.AccountAnalyticAccount.read.return_value = [
            {"id": 22, "code": "010102"}
        ]
        mappings = [("600.000.000.000", "010102-Aprovisionament")]
        rows = importer.resolve_mappings(client, mappings)
        self.assertEqual(
            [row["status"] for row in rows],
            ["ready"],
        )
        result = importer.create_defaults(client, rows)

        self.assertEqual(result, 1)
        client.AccountAnalyticDefault.create.assert_called_once_with({
            "account_id": 11,
            "analytic_id": 22,
            "sequence": 100,
        })
        self.assertEqual(rows[0]["status"], "created")

    def test_mapping_resolution_requires_exactly_one_account_and_analytic(self):
        client = self.client()
        client.AccountAccount.search.return_value = []
        client.AccountAnalyticAccount.search.return_value = []

        rows = importer.resolve_mappings(
            client,
            [("600.000.000.000", "010102-Aprovisionament")],
        )

        client.AccountAccount.search.assert_called_once_with([])
        client.AccountAnalyticAccount.search.assert_called_once_with([])
        self.assertEqual(rows[0]["status"], "skipped")
        self.assertIn("account_not_found", rows[0]["detail"])
        self.assertIn("analytic_not_found", rows[0]["detail"])

    def test_missing_mapping_does_not_block_existing_account_and_analytic(self):
        client = self.client()
        client.AccountAccount.search.return_value = [11]
        client.AccountAccount.read.return_value = [
            {"id": 11, "code": "600000000000"}
        ]
        client.AccountAnalyticAccount.search.return_value = [22]
        client.AccountAnalyticAccount.read.return_value = [
            {"id": 22, "code": "010102"}
        ]

        rows = importer.resolve_mappings(
            client,
            [
                ("600.000.000.000", "010102-Aprovisionament"),
                ("601.000.000.000", "010102-Aprovisionament"),
            ],
        )

        self.assertEqual(
            [row["status"] for row in rows],
            ["ready", "skipped"],
        )
        self.assertIn("account_not_found", rows[1]["detail"])

    def test_resolution_matches_analytic_code_from_utf8_mapping(self):
        client = self.client()
        client.AccountAccount.search.return_value = [11]
        client.AccountAccount.read.return_value = [
            {"id": 11, "code": "600000000000"}
        ]
        client.AccountAnalyticAccount.search.return_value = [22]
        client.AccountAnalyticAccount.read.return_value = [
            {"id": 22, "code": "010201"}
        ]

        rows = importer.resolve_mappings(
            client,
            [("600.000.000.000", "010201-Representació")],
        )

        self.assertEqual(
            rows[0]["analytic_code"],
            "010201",
        )

    def test_analytic_account_is_resolved_by_six_digit_code(self):
        client = self.client()
        client.AccountAccount.search.return_value = [11]
        client.AccountAccount.read.return_value = [
            {"id": 11, "code": "600000000000"}
        ]
        client.AccountAnalyticAccount.search.return_value = [22]
        client.AccountAnalyticAccount.read.return_value = [
            {"id": 22, "code": "040402"}
        ]

        rows = importer.resolve_mappings(
            client,
            [("600.000.000.000", "040402-Gestor d'autoconsum")],
        )

        self.assertEqual(
            rows[0]["status"],
            "ready",
        )

    def test_existing_default_is_reported_and_not_duplicated(self):
        client = self.client()
        client.AccountAccount.search.return_value = [11]
        client.AccountAccount.read.return_value = [
            {"id": 11, "code": "600000000000"}
        ]
        client.AccountAnalyticAccount.search.return_value = [22]
        client.AccountAnalyticAccount.read.return_value = [
            {"id": 22, "code": "010102"}
        ]
        client.AccountAnalyticDefault.search.return_value = [33]
        client.AccountAnalyticDefault.read.return_value = [{
            "id": 33,
            "account_id": [11, "600000000000"],
            "analytic_id": [22, "010102-Aprovisionament"],
            "product_id": False,
            "partner_id": False,
            "user_id": False,
            "company_id": False,
            "date_start": False,
            "date_stop": False,
        }]

        rows = importer.resolve_mappings(
            client,
            [("600.000.000.000", "010102-Aprovisionament")],
        )
        created = importer.create_defaults(client, rows)

        self.assertEqual(rows[0]["status"], "already_exists")
        self.assertEqual(created, 0)
        client.AccountAnalyticDefault.create.assert_not_called()

    def test_report_csv_contains_created_and_skipped_rows(self):
        with temporary_directory() as parent:
            report = os.path.join(parent, "report.csv")
            rows = [
                {
                    "account_code_csv": "600.000.000.000",
                    "account_code_erp": "600000000000",
                    "analytic_mapping_csv": "010102-Aprovisionament",
                    "analytic_code": "010102",
                    "account_id": 11,
                    "analytic_id": 22,
                    "status": "created",
                    "detail": "",
                },
                {
                    "account_code_csv": "601.000.000.000",
                    "account_code_erp": "601000000000",
                    "analytic_mapping_csv": "999999-Unknown",
                    "analytic_code": "999999",
                    "account_id": "",
                    "analytic_id": "",
                    "status": "skipped",
                    "detail": "analytic_not_found",
                },
            ]

            importer.write_report(report, rows)
            header, records = read_csv(report)

        self.assertEqual(header[-2:], ["status", "detail"])
        self.assertEqual([row["status"] for row in records], ["created", "skipped"])


if __name__ == "__main__":
    import unittest

    unittest.main()
