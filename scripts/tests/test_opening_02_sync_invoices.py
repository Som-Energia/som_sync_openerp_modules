# -*- coding: utf-8 -*-
"""Proves de les peticions async de fase 2, sense ERP ni RQ."""

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
    Mock, Namespace, SCRIPTS, StringIO, TestCase, call, patch, read_text,
    redirect_stderr, redirect_stdout, temporary_directory, write_text,
)

with patch.object(sys, "path", [SCRIPTS] + sys.path):
    import opening_02_sync_invoices as syncer


def manifest(ids):
    return {"metadata": {"format_version": 1, "phase": "identify_invoice_ids",
                         "model": "account.invoice", "invoice_count": len(ids)},
            "invoice_ids": ids}


class OpeningSyncTest(TestCase):
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
            source = os.path.join(parent, "invoice_ids.json")
            write_text(source, json.dumps(payload))
            with patch.dict(sys.modules, modules), redirect_stdout(stdout), \
                    redirect_stderr(stderr), patch.object(syncer.logging, "basicConfig"):
                result = syncer.main(["--input", str(source)])
            self.assertEqual(json.loads(read_text(source)), payload)
            self.assertEqual(os.listdir(parent), [os.path.basename(source)])
        return result, client, factory, config, stdout.getvalue(), stderr.getvalue()

    def test_async_none_results_are_completed_calls_not_confirmed_jobs(self):
        result, client, factory, config, stdout, stderr = self.run_main(
            manifest([1, 2]), [(True, False, True), (None, None), None])
        self.assertEqual(result, 0)
        factory.assert_called_once_with(**config)
        self.assertEqual(client.execute.call_args_list, [
            call("odoo.sync", "sync_model_enabled_amplified", "account.invoice"),
            call("odoo.sync", "common_sync_model_create_update", "account.invoice", "sync", 1),
            call("odoo.sync", "common_sync_model_create_update", "account.invoice", "sync", 2),
        ])
        self.assertIn("2 crides sense error RPC; 0 crides amb error RPC", stdout)
        self.assertIn("no implica encuaments confirmats", stdout)
        self.assertEqual(stderr, "")
        self.assertNotIn(config["password"], stdout)

    def test_rpc_failures_are_identified_without_retry_and_remaining_ids_are_attempted(self):
        result, client, _, _, stdout, stderr = self.run_main(
            manifest([1, 2, 3, 4]),
            [(True, True, True), Fault(1, "fallada ERP"), (None, None),
             OSError("connexió interrompuda"), (None, None)])
        self.assertEqual(result, 1)
        self.assertEqual(client.execute.call_count, 5)
        self.assertIn("2 crides sense error RPC; 2 crides amb error RPC", stdout)
        self.assertIn("IDs amb error RPC: 1, 3", stderr)
        self.assertEqual([item[0][-1] for item in client.execute.call_args_list[1:]], [1, 2, 3, 4])

    def test_disabled_or_synchronous_configuration_stops_before_submitting(self):
        for config in [(False, False, False), (True, True, False)]:
            result, client, _, _, _, stderr = self.run_main(manifest([1]), [config])
            self.assertEqual(result, 1)
            self.assertIn("habilitat per sincronitzar en async", stderr)
            self.assertEqual(client.execute.call_count, 1)

    def test_preflight_rpc_error_stops_before_submitting(self):
        result, client, _, _, _, stderr = self.run_main(
            manifest([1]), [Fault(1, "sense permisos")])
        self.assertEqual(result, 1)
        self.assertIn("sense permisos", stderr)
        self.assertEqual(client.execute.call_count, 1)

    def test_empty_manifest_does_not_connect(self):
        result, client, factory, _, stdout, _ = self.run_main(manifest([]), [])
        self.assertEqual(result, 0)
        factory.assert_not_called()
        client.execute.assert_not_called()
        self.assertIn("0 IDs; 0 crides sense error RPC; 0 crides amb error RPC", stdout)

    def test_invalid_manifests_are_rejected_before_connecting(self):
        invalid = [[], {}, {"metadata": []}]
        for ids in ([1, 1], [True], [0], [-1], [1.5], ["1"], None):
            payload = manifest([])
            payload["invoice_ids"] = ids
            invalid.append(payload)
        for key, value in [("model", "res.partner"), ("phase", "other"),
                           ("format_version", 2), ("format_version", True),
                           ("invoice_count", 99), ("invoice_count", True)]:
            payload = copy.deepcopy(manifest([1]))
            payload["metadata"][key] = value
            invalid.append(payload)
        for payload in invalid:
            result, client, factory, _, _, stderr = self.run_main(payload, [])
            self.assertEqual(result, 1)
            factory.assert_not_called()
            client.execute.assert_not_called()
            self.assertIn("No s'ha pogut completar la fase 2", stderr)

    def test_missing_or_malformed_input_is_reported(self):
        with temporary_directory() as parent:
            source = os.path.join(parent, "invoice_ids.json")
            for content in (None, "{JSON incorrecte"):
                if content is not None:
                    write_text(source, content)
                with redirect_stderr(StringIO()) as stderr:
                    result = syncer.main(["--input", str(source)])
                self.assertEqual(result, 1)
                self.assertIn("No s'ha pogut completar la fase 2", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
