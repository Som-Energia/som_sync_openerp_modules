# -*- coding: utf-8 -*-
"""Tests for importing account analytic defaults from the mapping CSV."""

from __future__ import print_function, unicode_literals

import os
import sys

from opening_test_support import (
    Mock, SCRIPTS, TestCase, patch, temporary_directory,
    write_text,
)

with patch.object(sys, "path", [SCRIPTS] + sys.path):
    import import_account_analytic_defaults as importer


class ImportAccountAnalyticDefaultsTest(TestCase):
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
        client = Mock()
        client.AccountAccount.search.return_value = [11]
        client.AccountAccount.read.return_value = [
            {"id": 11, "code": "600.000.000.000"}
        ]
        client.AccountAnalyticAccount.search.return_value = [22]
        client.AccountAnalyticAccount.read.return_value = [
            {"id": 22, "name": "010102-Aprovisionament"}
        ]
        mappings = [("600.000.000.000", "010102-Aprovisionament")]
        defaults = importer.resolve_mappings(client, mappings)
        self.assertEqual(
            defaults,
            [{"account_id": 11, "analytic_id": 22, "sequence": 100}],
        )

        client.AccountAnalyticDefault = Mock()
        client.AccountAnalyticDefault.create.return_value = 1

        result = importer.create_defaults(client, defaults)

        self.assertEqual(result, 1)
        client.AccountAnalyticDefault.create.assert_called_once_with(defaults[0])
        self.assertEqual(defaults[0]["sequence"], 100)

    def test_mapping_resolution_requires_exactly_one_account_and_analytic(self):
        client = Mock()
        client.AccountAccount.search.return_value = []
        client.AccountAnalyticAccount.search.return_value = []

        with self.assertRaisesRegex(ValueError, "OpenERP account code .* not found"):
            importer.resolve_mappings(
                client,
                [("600.000.000.000", "010102-Aprovisionament")],
            )

        client.AccountAccount.search.assert_called_once_with([])
        client.AccountAnalyticAccount.search.assert_called_once_with([])

    def test_resolution_matches_utf8_analytic_names(self):
        client = Mock()
        client.AccountAccount.search.return_value = [11]
        client.AccountAccount.read.return_value = [
            {"id": 11, "code": "600.000.000.000"}
        ]
        client.AccountAnalyticAccount.search.return_value = [22]
        client.AccountAnalyticAccount.read.return_value = [
            {"id": 22, "name": "010201-Representació".encode("utf-8")}
        ]

        defaults = importer.resolve_mappings(
            client,
            [("600.000.000.000", "010201-Representació")],
        )

        self.assertEqual(
            defaults,
            [{"account_id": 11, "analytic_id": 22, "sequence": 100}],
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
