# -*- coding: utf-8 -*-
"""Proves de peticions async d'acords, sense ERP ni RQ."""

from __future__ import print_function, unicode_literals

import copy
import json
import os
import sys
import unittest
try:
    from xmlrpc.client import Fault
except ImportError:
    from xmlrpclib import Fault
from opening_test_support import (
    Mock, Namespace, SCRIPTS, StringIO, TestCase, call, patch, read_bytes,
    redirect_stderr, redirect_stdout, temporary_directory, write_text,
)

with patch.object(sys, "path", [SCRIPTS] + sys.path):
    import opening_04_sync_fraccionaments as syncer


def manifest(ids):
    return {"metadata": {"format_version": 1, "phase": "identify_fraccionament_ids",
                         "model": "account.invoice.fraccionament", "fraccionament_count": len(ids)},
            "fraccionament_ids": ids, "invoice_ids": [7001]}


class OpeningFraccionamentSyncTest(TestCase):
    def run_main(self, payload, responses):
        client = Mock()
        client.execute.side_effect = responses
        config = {"server": "http://erp-proves:8069", "db": "copia-proves",
                  "user": "proves", "password": "secret-proves"}
        factory = Mock(return_value=client)
        modules = {"dbconfig": Namespace(erppeek=config),
                   "erppeek": Namespace(Client=factory)}
        stdout, stderr = StringIO(), StringIO()
        with temporary_directory() as parent:
            source = os.path.join(parent, "fraccionament_ids.json")
            write_text(source, json.dumps(payload))
            original = read_bytes(source)
            with patch.dict(sys.modules, modules), redirect_stdout(stdout), \
                    redirect_stderr(stderr), patch.object(syncer.logging, "basicConfig"):
                result = syncer.main(["--input", source])
            self.assertEqual(read_bytes(source), original)
            self.assertEqual(os.listdir(parent), [os.path.basename(source)])
        return result, client, factory, config, stdout.getvalue(), stderr.getvalue()

    def test_submits_only_agreement_ids_without_forcing_sync_context_or_reading_states(self):
        result, client, factory, config, stdout, stderr = self.run_main(
            manifest([10, 11]), [(True, False, True), (True, False, False), (None, None), None])
        self.assertEqual(result, 0)
        factory.assert_called_once_with(**config)
        self.assertEqual(client.execute.call_args_list, [
            call("odoo.sync", "sync_model_enabled_amplified", "account.invoice.fraccionament"),
            call("odoo.sync", "sync_model_enabled_amplified", "account.invoice"),
            call("odoo.sync", "common_sync_model_create_update",
                 "account.invoice.fraccionament", "sync", 10),
            call("odoo.sync", "common_sync_model_create_update",
                 "account.invoice.fraccionament", "sync", 11),
        ])
        self.assertIn("2 acords; 2 crides sense error RPC; 0 crides amb error RPC", stdout)
        self.assertIn("no implica encuaments confirmats", stdout)
        self.assertEqual(stderr, "")
        self.assertNotIn(config["password"], stdout)

    def test_rpc_errors_do_not_retry_or_prevent_remaining_agreement_requests(self):
        result, client, _, _, stdout, stderr = self.run_main(
            manifest([10, 11, 12, 13]),
            [(True, True, True), (True, True, True), Fault(1, "fallada ERP"),
             (None, None), IOError("connexió interrompuda"), (None, None)])
        self.assertEqual(result, 1)
        self.assertIn("2 crides sense error RPC; 2 crides amb error RPC", stdout)
        self.assertIn("IDs d'acord amb error RPC: 10, 12", stderr)
        self.assertEqual([item[0][-1]
                         for item in client.execute.call_args_list[2:]], [10, 11, 12, 13])

    def test_agreements_must_be_enabled_and_async_before_any_submission(self):
        for config in [(False, False, False), (True, True, False)]:
            result, client, _, _, _, stderr = self.run_main(manifest([10]), [config])
            self.assertEqual(result, 1)
            self.assertEqual(client.execute.call_count, 1)
            self.assertIn("account.invoice.fraccionament ha d'estar habilitat en async", stderr)

    def test_disabled_original_invoice_model_stops_before_submitting(self):
        result, client, _, _, _, stderr = self.run_main(
            manifest([10]), [(True, True, True), (False, False, False)])
        self.assertEqual(result, 1)
        self.assertEqual(client.execute.call_count, 2)
        self.assertIn("account.invoice ha d'estar habilitat", stderr)

    def test_preflight_errors_stop_before_any_submission(self):
        for responses in [[Fault(1, "sense permisos")],
                          [(True, False, True), Fault(1, "sense permisos")]]:
            result, client, _, _, _, stderr = self.run_main(manifest([10]), responses)
            self.assertEqual(result, 1)
            self.assertEqual(client.execute.call_count, len(responses))
            self.assertIn("sense permisos", stderr)

    def test_empty_manifest_does_not_connect(self):
        result, client, factory, _, stdout, _ = self.run_main(manifest([]), [])
        self.assertEqual(result, 0)
        factory.assert_not_called()
        client.execute.assert_not_called()
        self.assertIn("0 acords; 0 crides sense error RPC; 0 crides amb error RPC", stdout)

    def test_wrong_model_phase_version_count_or_ids_are_rejected_before_connecting(self):
        invalid = [[], {}, {"metadata": []}]
        for ids in ([10, 10], [True], [0], [-1], [1.5], ["10"], None):
            payload = manifest([])
            payload["fraccionament_ids"] = ids
            invalid.append(payload)
        for key, value in [("model", "account.invoice"), ("phase", "identify_invoice_ids"),
                           ("format_version", 2), ("format_version", True),
                           ("fraccionament_count", 99), ("fraccionament_count", True)]:
            payload = copy.deepcopy(manifest([10]))
            payload["metadata"][key] = value
            invalid.append(payload)
        missing_ids = manifest([10])
        del missing_ids["fraccionament_ids"]
        invalid.append(missing_ids)
        for payload in invalid:
            result, client, factory, _, _, stderr = self.run_main(payload, [])
            self.assertEqual(result, 1)
            factory.assert_not_called()
            client.execute.assert_not_called()
            self.assertIn("No s'ha pogut completar la fase 4", stderr)

    def test_missing_or_malformed_file_is_reported(self):
        with temporary_directory() as parent:
            source = os.path.join(parent, "fraccionament_ids.json")
            for content in (None, "{JSON incorrecte"):
                if content is not None:
                    write_text(source, content)
                with redirect_stderr(StringIO()) as stderr:
                    result = syncer.main(["--input", source])
                self.assertEqual(result, 1)
                self.assertIn("No s'ha pogut completar la fase 4", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
