# -*- coding: utf-8 -*-
from __future__ import absolute_import

import mock

from destral import testing

from ..models import odoo_sync


class TestNorma57File(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.imd_obj = self.openerp.pool.get('ir.model.data')
        self.conf_obj = self.openerp.pool.get('res.config')
        self.n57_obj = self.openerp.pool.get('norma57.file')
        self.n57_line_obj = self.openerp.pool.get('norma57.file.line')
        self.ai_obj = self.openerp.pool.get('account.invoice')
        self.sync_obj = self.openerp.pool.get('odoo.sync')
        super(TestNorma57File, self).setUp()

    def _create_norma57_file(self, name='Norma57 test'):
        return self.n57_obj.create(self.cursor, self.uid, {
            'name': name,
            'header_presentation_date': '2026-01-15',
        })

    def _build_mock_line(
            self, resource_id, amount=100.0, state='confirmed', resource_model='account.invoice'):
        line = mock.Mock()
        line.state = state
        line.amount = amount
        line.resource = '{},{}'.format(resource_model, resource_id)
        return line

    def _create_norma57_sync(self, norma57_id, sync_state='synced'):
        return self.sync_obj._create_sync_record(
            self.cursor,
            self.uid,
            'norma57.file',
            norma57_id,
            321,
            '2026-01-15 10:00:00',
            {'sync_state': sync_state},
        )

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    def test_get_related_values_builds_simple_payment_order_payload(self, mock_sync):
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'invoice_0004'
        )[1]
        norma57_id = self._create_norma57_file()
        mock_line = self._build_mock_line(invoice_id, amount=125.5)
        self.conf_obj.set(self.cursor, self.uid, 'odoo_norma57_destination_journal', '17')
        self.conf_obj.set(self.cursor, self.uid, 'odoo_norma57_payment_method', '411')
        mock_sync.return_value = (99, invoice_id)

        with mock.patch.object(
                type(self.ai_obj),
                'process_lines_with_discrepancies') as mock_discrepancies:
            with mock.patch.object(self.n57_obj, 'browse') as mock_browse:
                norma57_file = mock.Mock()
                norma57_file.name = 'Norma57 test'
                norma57_file.header_presentation_date = '2026-01-15'
                norma57_file.lines = [mock_line]
                mock_browse.return_value = norma57_file
                related_values = self.n57_obj.get_related_values(self.cursor, self.uid, norma57_id)

        self.assertEqual(related_values, {
            'destination_journal_id': 17,
            'payment_method_line_id': 411,
            'name': 'Norma57 test',
            'sdd_required_collection_date': '2026-01-15',
            'amount': 125.5,
            'lines': [{
                'invoice_id': 99,
                'amount': 125.5,
            }],
        })
        mock_discrepancies.assert_called_once_with(
            self.cursor, self.uid, [invoice_id], [{'invoice_id': 99, 'amount': 125.5}],
            is_grouped=False, context={}
        )

    def test_get_line_invoice_erp_id_raises_when_resource_is_not_supported(self):
        line = mock.Mock()
        line.resource = 'fake.model,7'

        with self.assertRaises(Exception):
            self.n57_obj._get_line_invoice_erp_id(self.cursor, self.uid, line)

    def test_get_line_invoice_erp_id_returns_invoice_from_giscedata_factura(self):
        line = mock.Mock()
        line.resource = 'giscedata.facturacio.factura,7'
        factura_obj = mock.Mock()
        factura_obj.read.return_value = {'invoice_id': (42, 'INV/42')}

        with mock.patch.object(self.n57_obj.pool, 'get', return_value=factura_obj) as mock_get:
            invoice_id = self.n57_obj._get_line_invoice_erp_id(self.cursor, self.uid, line)

        self.assertEqual(invoice_id, 42)
        mock_get.assert_called_once_with('giscedata.facturacio.factura')
        factura_obj.read.assert_called_once_with(
            self.cursor, self.uid, 7, ['invoice_id'], context={}
        )

    def test_get_line_invoice_erp_id_returns_false_when_resource_is_empty(self):
        line = mock.Mock()
        line.resource = False

        invoice_id = self.n57_obj._get_line_invoice_erp_id(self.cursor, self.uid, line)

        self.assertFalse(invoice_id)

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    def test_get_related_values_raises_when_destination_journal_is_missing(self, mock_sync):
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'invoice_0004'
        )[1]
        norma57_id = self._create_norma57_file()
        mock_line = self._build_mock_line(invoice_id)
        self.conf_obj.set(self.cursor, self.uid, 'odoo_norma57_destination_journal', '0')
        self.conf_obj.set(self.cursor, self.uid, 'odoo_norma57_payment_method', '411')
        mock_sync.return_value = (99, invoice_id)

        with mock.patch.object(type(self.ai_obj), 'process_lines_with_discrepancies'):
            with mock.patch.object(self.n57_obj, 'browse') as mock_browse:
                norma57_file = mock.Mock()
                norma57_file.name = 'Norma57 test'
                norma57_file.header_presentation_date = '2026-01-15'
                norma57_file.lines = [mock_line]
                mock_browse.return_value = norma57_file
                with self.assertRaises(Exception):
                    self.n57_obj.get_related_values(self.cursor, self.uid, norma57_id)

    def test_get_related_values_raises_when_no_confirmed_lines_are_syncable(self):
        norma57_id = self._create_norma57_file()
        self.conf_obj.set(self.cursor, self.uid, 'odoo_norma57_destination_journal', '17')
        self.conf_obj.set(self.cursor, self.uid, 'odoo_norma57_payment_method', '411')

        with mock.patch.object(self.n57_obj, 'browse') as mock_browse:
            norma57_file = mock.Mock()
            norma57_file.name = 'Norma57 test'
            norma57_file.header_presentation_date = '2026-01-15'
            norma57_file.lines = []
            mock_browse.return_value = norma57_file
            with self.assertRaises(Exception):
                self.n57_obj.get_related_values(self.cursor, self.uid, norma57_id)

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    def test_confirm_triggers_norma57_sync(self, mock_sync):
        norma57_id = self._create_norma57_file()

        result = self.n57_obj.confirm(self.cursor, self.uid, norma57_id)

        self.assertTrue(result)
        mock_sync.assert_called_once_with(
            self.cursor, self.uid, 'norma57.file', 'write', norma57_id, context={}
        )

    def test_get_payment_entry_erp_id_uses_offset(self):
        self.assertEqual(self.n57_obj._get_payment_entry_erp_id(17), 900000017)

    def test_get_payment_entry_account_code_pattern_uses_like_format(self):
        self.assertEqual(
            self.n57_obj._get_payment_entry_account_code_pattern('572.9'),
            '572%9'
        )
        self.assertEqual(
            self.n57_obj._get_payment_entry_account_code_pattern('570.0'),
            '570%0'
        )

    def test_sync_norma57_payment_entry_if_needed_skips_when_entry_already_exists(self):
        norma57_id = self._create_norma57_file()
        sync_id = self._create_norma57_sync(norma57_id)
        self.sync_obj.write(self.cursor, self.uid, [sync_id], {
            'pnt_norma57_payment_entry_odoo_id': 888,
        })

        result = self.n57_obj._sync_norma57_payment_entry_if_needed(
            self.cursor, self.uid, norma57_id)

        self.assertEqual(result, 888)

    def test_sync_norma57_payment_entry_if_needed_stores_created_odoo_id(self):
        norma57_id = self._create_norma57_file()
        sync_id = self._create_norma57_sync(norma57_id)

        with mock.patch.object(self.n57_obj, '_build_payment_entry_payload') as mock_payload:
            with mock.patch.object(self.n57_obj, '_create_payment_entry_in_odoo') as mock_create:
                mock_payload.return_value = {'pnt_erp_id': 900000001}
                mock_create.return_value = {
                    'success': True,
                    'odoo_id': 4321,
                    'response_text': '{"ok": true}',
                    'url': 'http://odoo/api/v1/entries',
                }

                result = self.n57_obj._sync_norma57_payment_entry_if_needed(
                    self.cursor, self.uid, norma57_id)

        sync_record = self.sync_obj.browse(self.cursor, self.uid, sync_id)
        self.assertEqual(result, 4321)
        self.assertEqual(sync_record.pnt_norma57_payment_entry_odoo_id, 4321)
        self.assertEqual(sync_record.pnt_norma57_payment_entry_last_result, '{"ok": true}')

    def test_sync_norma57_payment_entry_if_needed_recovers_duplicate_entry_odoo_id(self):
        norma57_id = self._create_norma57_file()
        sync_id = self._create_norma57_sync(norma57_id)

        with mock.patch.object(self.n57_obj, '_build_payment_entry_payload') as mock_payload:
            with mock.patch.object(self.n57_obj, '_create_payment_entry_in_odoo') as mock_create:
                with mock.patch.object(
                        self.n57_obj,
                        '_get_existing_payment_entry_odoo_id') as mock_get:
                    mock_payload.return_value = {'pnt_erp_id': 900000001}
                    mock_create.return_value = {
                        'success': False,
                        'odoo_id': False,
                        'response_text': '{"error_code": "DUPLICATE_KEY_VALUE"}',
                        'url': 'http://odoo/api/v1/entries',
                    }
                    mock_get.return_value = 7654

                    result = self.n57_obj._sync_norma57_payment_entry_if_needed(
                        self.cursor, self.uid, norma57_id)

        sync_record = self.sync_obj.browse(self.cursor, self.uid, sync_id)
        self.assertEqual(result, 7654)
        self.assertEqual(sync_record.pnt_norma57_payment_entry_odoo_id, 7654)
        self.assertEqual(
            sync_record.pnt_norma57_payment_entry_last_result,
            '{"error_code": "DUPLICATE_KEY_VALUE"}'
        )

    def test_sync_norma57_payment_entry_if_needed_stores_last_result_on_error(self):
        norma57_id = self._create_norma57_file()
        sync_id = self._create_norma57_sync(norma57_id)

        with mock.patch.object(self.n57_obj, '_build_payment_entry_payload') as mock_payload:
            with mock.patch.object(self.n57_obj, '_create_payment_entry_in_odoo') as mock_create:
                mock_payload.return_value = {'pnt_erp_id': 900000001}
                mock_create.return_value = {
                    'success': False,
                    'odoo_id': False,
                    'response_text': 'boom',
                    'url': 'http://odoo/api/v1/entries',
                }

                result = self.n57_obj._sync_norma57_payment_entry_if_needed(
                    self.cursor, self.uid, norma57_id)

        sync_record = self.sync_obj.browse(self.cursor, self.uid, sync_id)
        self.assertFalse(result)
        self.assertFalse(sync_record.pnt_norma57_payment_entry_odoo_id)
        self.assertEqual(sync_record.pnt_norma57_payment_entry_last_result, 'boom')

    @mock.patch.object(odoo_sync.OdooSync, 'poll_payment_order_status_sync')
    def test_update_pending_state_sync_triggers_payment_entry_sync_after_poll(
            self, mock_poll):
        norma57_id = self._create_norma57_file()
        mock_poll.return_value = True

        with mock.patch.object(
                type(self.n57_obj),
                '_sync_norma57_payment_entry_if_needed') as mock_payment_entry_sync:
            result = self.n57_obj.update_pending_state_sync(self.cursor, self.uid, norma57_id)

        self.assertTrue(result)
        mock_payment_entry_sync.assert_called_once_with(
            self.cursor, self.uid, norma57_id, context={}
        )
