# -*- coding: utf-8 -*-
"""Regressions de compatibilitat Unicode, dates i enters entre Python 2.7 i 3."""

from __future__ import print_function, unicode_literals

import os
import sys
import unittest

from opening_test_support import (
    SCRIPTS, StringIO, TestCase, patch, read_bytes, read_csv, temporary_directory,
)

with patch.object(sys, "path", [SCRIPTS] + sys.path):
    import opening_common as common


class OpeningCompatibilityTest(TestCase):
    def test_integer_ids_include_long_but_exclude_booleans(self):
        self.assertTrue(common.is_integer(common.integer_types[-1](1)))
        self.assertTrue(common.is_integer(2 ** 40))
        for value in (True, False, "1", 1.0, None):
            self.assertFalse(common.is_integer(value))

    def test_date_parser_is_strict_and_utc_timestamp_keeps_offset(self):
        self.assertEqual(common.parse_date("2024-02-29").isoformat(), "2024-02-29")
        for value in ("2026-02-29", "2026-1-01", "2026-01-1", "20260101"):
            with self.assertRaises(ValueError):
                common.parse_date(value)
        self.assertTrue(common.utc_now().endswith("+00:00"))

    def test_utf8_files_and_paths_preserve_accents_quotes_and_newlines(self):
        value = 'Quota; "cobrada"\nValència €'
        with temporary_directory() as parent:
            json_path = os.path.join(parent, "assaig-à.json")
            csv_path = os.path.join(parent, "assaig-à.csv")
            payload = {"text": value, "ids": [1, 2 ** 40]}
            common.write_json(json_path, payload)
            self.assertEqual(common.read_json(json_path), payload)
            self.assertIn("València €".encode("utf-8"), read_bytes(json_path))
            common.write_csv(csv_path, ["text", "amount"], [{"text": value, "amount": "0.30"}])
            fields, rows = read_csv(csv_path)
            self.assertEqual(fields, ["text", "amount"])
            self.assertEqual(rows, [{"text": value, "amount": "0.30"}])
            self.assertNotIn(b"\r\r\n", read_bytes(csv_path))

    def test_console_output_is_utf8_and_preserves_empty_messages(self):
        output = StringIO()
        common.print_message("Connexió establerta: €", file=output)
        common.print_message("", file=output)
        self.assertEqual(output.getvalue(), "Connexió establerta: €\n\n")


if __name__ == "__main__":
    unittest.main()
