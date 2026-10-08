# -*- coding: utf-8 -*-
from __future__ import absolute_import

import json
import mock
import netsvc

from destral import testing


class TestTpvPayment(testing.OOTestCaseWithCursor):

    def setUp(self):
        super(TestTpvPayment, self).setUp()
        self.invoice_obj = self.openerp.pool.get('account.invoice')
        self.move_obj = self.openerp.pool.get('account.move')
        self.sync_obj = self.openerp.pool.get('odoo.sync')
        self.journal_obj = self.openerp.pool.get('account.journal')
        self.imd_obj = self.openerp.pool.get('ir.model.data')
        self.invoice_id = self._ref('invoice_0001')
        self.journal_id = self._ref('account_journal_syncronizable')
        self.period_id = self._ref('period_012026')
        self.journal_obj.write(self.cursor, self.uid, self.journal_id, {
            'name': 'TPV Triodos',
        })
        self.account_id = self.openerp.pool.get('account.account').search(
            self.cursor, self.uid, [('code', '=', '570000')])[0]
        netsvc.LocalService('workflow').trg_validate(
            self.uid, 'account.invoice', self.invoice_id, 'invoice_open', self.cursor)
        invoice = self.invoice_obj.browse(self.cursor, self.uid, self.invoice_id)
        self.partner_id = invoice.partner_id.id
        self._map('account.invoice', self.invoice_id, 901)
        self._map('account.journal', self.journal_id, 902)
        self._map('res.partner', self.partner_id, 903)
        partner_lookup = mock.patch.object(
            self.sync_obj, 'get_odoo_id_by_erp_id_from_odoo', return_value=(903, True))
        partner_lookup.start()
        self.addCleanup(partner_lookup.stop)
        self.openerp.pool.get('odoo.sync.model.config').write(
            self.cursor, self.uid, self._ref('odoo_sync_model_config_account_move'), {
                'auto_sync': True, 'async_enabled': True,
            })

    def _ref(self, name):
        return self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', name)[1]

    def _map(self, model, erp_id, odoo_id):
        return self.sync_obj.get_or_create_static_odoo_id(
            self.cursor, self.uid, model, erp_id, odoo_id)

    def _collect(self, amount=1000.0):
        return self.invoice_obj.pay_and_reconcile(
            self.cursor, self.uid, [self.invoice_id], amount, self.account_id,
            self.period_id, self.journal_id, False, self.period_id, False,
            context={'date_p': '2026-01-20'})

    def _payload(self, move_id):
        return self.sync_obj.get_model_vals_to_sync(
            self.cursor, self.uid, 'account.move', move_id)

    def test_collection_enqueues_once_after_reconciliation_and_noop_does_not(self):
        observations = []

        def observe_collection(cr, uid, model, action, move_id, context=None):
            invoice = self.invoice_obj.browse(cr, uid, self.invoice_id)
            observations.append((model, move_id, invoice.state, invoice.payment_ids))

        with mock.patch.object(self.sync_obj, 'syncronize', side_effect=observe_collection):
            move_id = self._collect()
            self.assertIs(self._collect(), True)
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0][:3], ('account.move', move_id, 'paid'))
        self.assertTrue(observations[0][3])

    def test_payload_uses_move_identity_mapped_journal_and_actual_collection(self):
        with mock.patch.object(self.sync_obj, 'syncronize'):
            move_id = self._collect()
        invoice = self.invoice_obj.browse(self.cursor, self.uid, self.invoice_id)
        self.assertEqual(self._payload(move_id), {
            'pnt_source_model': 'account.move',
            'pnt_erp_id': move_id,
            'journal_id': 902,
            'date': '2026-01-20',
            'amount': 1000.0,
            'partner_id': 903,
            'payment_ref': '[FACTURA] {}'.format(invoice.number),
        })
        self.assertEqual(self.move_obj.get_mapping_model_post(
            self.cursor, self.uid, move_id), 'bank_statement_lines')

    @mock.patch('som_sync_openerp.models.odoo_sync.requests.post')
    def test_retries_send_same_statement_identity_and_store_diagnostics(self, post):
        with mock.patch.object(self.sync_obj, 'syncronize'):
            move_id = self._collect()
        response = {'success': True, 'data': {'odoo_id': 904, 'erp_id': move_id}}
        post.return_value.status_code = 201
        post.return_value.json.return_value = response
        post.return_value.text = json.dumps(response)
        for _ in range(2):
            self.assertEqual(self.sync_obj.syncronize_sync(
                self.cursor, self.uid, 'account.move', 'sync', move_id), (904, move_id))
        self.assertEqual(post.call_count, 2)
        first_request, retry = post.call_args_list
        self.assertEqual(first_request, retry)
        self.assertTrue(first_request[0][0].endswith('/bank_statement_lines'))
        sync_id = self.sync_obj.search(self.cursor, self.uid, [
            ('model.model', '=', 'account.move'), ('res_id', '=', move_id),
        ])[0]
        sync = self.sync_obj.browse(self.cursor, self.uid, sync_id)
        self.assertEqual(sync.odoo_id, 904)
        self.assertEqual(sync.sync_state, 'synced')
        self.assertEqual(json.loads(sync.odoo_last_sync_request), self._payload(move_id))

    def test_missing_journal_mapping_is_reported_without_undoing_collection(self):
        sync_id = self.sync_obj.search(self.cursor, self.uid, [
            ('model.model', '=', 'account.journal'), ('res_id', '=', self.journal_id),
        ])
        self.sync_obj.unlink(self.cursor, self.uid, sync_id)
        with mock.patch.object(self.sync_obj, 'syncronize'):
            move_id = self._collect()
        result = self.sync_obj.syncronize_sync(
            self.cursor, self.uid, 'account.move', 'sync', move_id)
        self.assertFalse(result[0])
        sync_id = self.sync_obj.search(self.cursor, self.uid, [
            ('model.model', '=', 'account.move'), ('res_id', '=', move_id),
        ])[0]
        self.assertEqual(self.sync_obj.browse(self.cursor, self.uid, sync_id).sync_state, 'error')
        self.assertEqual(self.invoice_obj.browse(
            self.cursor, self.uid, self.invoice_id).state, 'paid')

    def test_missing_invoice_dependency_prevents_statement_request(self):
        with mock.patch.object(self.sync_obj, 'syncronize'):
            move_id = self._collect()
        with mock.patch.object(self.sync_obj, 'common_sync_model_create_update',
                               return_value=(False, False)):
            with self.assertRaisesRegexp(ValueError, 'invoice must be synchronized'):
                self._payload(move_id)

    @mock.patch('som_sync_openerp.models.odoo_sync.requests.post')
    def test_rejected_invoice_and_cached_retries_block_collection_until_fixed(self, post):
        with mock.patch.object(self.sync_obj, 'syncronize'):
            move_id = self._collect()
        invoice_sync_ids = self.sync_obj.search(self.cursor, self.uid, [
            ('model.model', '=', 'account.invoice'), ('res_id', '=', self.invoice_id),
        ])
        self.sync_obj.unlink(self.cursor, self.uid, invoice_sync_ids)
        invoice_response = {'success': True, 'data': {
            'odoo_id': 901,
            'erp_id': self.invoice_id,
            'metadata': [{
                'pnt_amount_total_erp_difference': 1.0,
                'move_type': 'out_invoice',
            }],
        }}
        post.return_value.status_code = 201
        post.return_value.json.return_value = invoice_response
        post.return_value.text = json.dumps(invoice_response)
        prepare_payload = self.sync_obj.get_model_vals_to_sync

        def payload(cr, uid, model, erp_id, context=None):
            if model == 'account.invoice':
                return {'pnt_erp_id': erp_id}
            return prepare_payload(cr, uid, model, erp_id, context=context)

        with mock.patch.object(self.sync_obj, 'get_model_vals_to_sync', side_effect=payload):
            for _ in range(2):
                result = self.sync_obj.syncronize_sync(
                    self.cursor, self.uid, 'account.move', 'sync', move_id)
                self.assertFalse(result[0])
                invoice_sync_id = self.sync_obj.search(self.cursor, self.uid, [
                    ('model.model', '=', 'account.invoice'),
                    ('res_id', '=', self.invoice_id),
                ])[0]
                invoice_sync = self.sync_obj.browse(self.cursor, self.uid, invoice_sync_id)
                self.assertEqual(invoice_sync.odoo_id, 901)
                self.assertEqual(invoice_sync.sync_state, 'error')
                move_sync_id = self.sync_obj.search(self.cursor, self.uid, [
                    ('model.model', '=', 'account.move'), ('res_id', '=', move_id),
                ])[0]
                move_sync = self.sync_obj.browse(self.cursor, self.uid, move_sync_id)
                self.assertEqual(move_sync.sync_state, 'error')
            post.assert_called_once()
            self.assertTrue(post.call_args[0][0].endswith('/invoices'))

            self.sync_obj.write(self.cursor, self.uid, invoice_sync_id, {'sync_state': 'synced'})
            statement_response = {'success': True, 'data': {'odoo_id': 904, 'erp_id': move_id}}
            post.return_value.json.return_value = statement_response
            post.return_value.text = json.dumps(statement_response)
            self.assertEqual(self.sync_obj.syncronize_sync(
                self.cursor, self.uid, 'account.move', 'sync', move_id), (904, move_id))
            self.assertTrue(post.call_args[0][0].endswith('/bank_statement_lines'))
            self.assertEqual(post.call_count, 2)

    def test_invoice_sync_with_accepted_warning_adjusts_collection_amount(self):
        with mock.patch.object(self.sync_obj, 'syncronize'):
            move_id = self._collect()
        invoice_sync_id = self.sync_obj.search(self.cursor, self.uid, [
            ('model.model', '=', 'account.invoice'), ('res_id', '=', self.invoice_id),
        ])[0]
        self.sync_obj.write(self.cursor, self.uid, invoice_sync_id, {
            'sync_state': 'synced_with_warning',
            'odoo_last_update_result': json.dumps({'data': {'metadata': [{
                'pnt_amount_total_erp_difference': 0.01,
                'move_type': 'out_invoice',
            }]}}),
        })
        self.assertEqual(self._payload(move_id)['amount'], 1000.01)

    def test_partial_collection_is_not_exported_as_a_full_invoice_payment(self):
        with mock.patch.object(self.sync_obj, 'syncronize'):
            move_id = self._collect(500.0)
        with self.assertRaisesRegexp(ValueError, 'fully reconciled'):
            self._payload(move_id)

    def test_final_installment_is_not_exported_as_a_full_invoice_payment(self):
        with mock.patch.object(self.sync_obj, 'syncronize'):
            self._collect(200.0)
            move_id = self._collect(800.0)
        with self.assertRaisesRegexp(ValueError, 'Only full, individual'):
            self._payload(move_id)

    def test_ambiguous_invoice_link_is_rejected(self):
        with mock.patch.object(self.sync_obj, 'syncronize'):
            move_id = self._collect()
        with mock.patch.object(self.invoice_obj, '_get_invoice_from_line',
                               return_value=[self.invoice_id, self._ref('invoice_0002')]):
            with self.assertRaisesRegexp(ValueError, 'exactly one invoice'):
                self._payload(move_id)

    def test_existing_generic_entry_requires_review_instead_of_double_export(self):
        with mock.patch.object(self.sync_obj, 'syncronize'):
            move_id = self._collect()
        self._map('account.move', move_id, 905)
        sync_id = self.sync_obj.search(self.cursor, self.uid, [
            ('model.model', '=', 'account.move'), ('res_id', '=', move_id),
        ])[0]
        self.sync_obj.write(self.cursor, self.uid, sync_id, {
            'odoo_last_sync_endpoint': 'http://odoo/api/v1/entries',
        })
        with self.assertRaisesRegexp(ValueError, 'already exported as an entry'):
            self._payload(move_id)

    def test_572_collection_routes_to_statements_but_other_journals_remain_blocked(self):
        with mock.patch.object(self.sync_obj, 'syncronize'):
            move_id = self._collect()
        account_obj = self.openerp.pool.get('account.account')
        account_obj.write(self.cursor, self.uid, self.account_id, {'code': '572000TEST'})
        self.assertTrue(self.move_obj.check_special_restrictions(
            self.cursor, self.uid, move_id))
        self.journal_obj.write(self.cursor, self.uid, self.journal_id, {'name': 'Other bank'})
        self.assertFalse(self.move_obj.check_special_restrictions(
            self.cursor, self.uid, move_id))
        self.assertEqual(self.move_obj.get_mapping_model_post(
            self.cursor, self.uid, move_id), 'entries')
