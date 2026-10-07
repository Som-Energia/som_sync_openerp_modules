# -*- coding: utf-8 -*-
from __future__ import absolute_import

import json
import mock

from destral import testing
from ..models import odoo_sync


class TestNorma57File(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.conf_obj = self.openerp.pool.get('res.config')
        self.n57_line_obj = self.openerp.pool.get('norma57.file.line')
        self.ai_obj = self.openerp.pool.get('account.invoice')
        super(TestNorma57File, self).setUp()

    def test_line_payload_uses_its_own_identity(self):
        self.conf_obj.set(
            self.cursor, self.uid, 'odoo_norma57_destination_journal', '17')
        norma57_file = mock.Mock(header_presentation_date='2026-01-15')
        line = mock.Mock(id=81, amount=-25.5, file_id=norma57_file)

        with mock.patch.object(
                self.n57_line_obj, '_get_invoice_erp_id', return_value=42):
            with mock.patch.object(self.n57_line_obj, 'browse', return_value=line):
                with mock.patch.object(
                        self.ai_obj, 'read', return_value={
                            'number': 'INV/2026/001', 'amount_total': 25.5}):
                    values = self.n57_line_obj.get_related_values(
                        self.cursor, self.uid, line.id)

        self.assertEqual(values, {
            'journal_id': 17,
            'date': '2026-01-15',
            'amount': 25.5,
            'payment_ref': '[FACTURA] INV/2026/001',
        })

    @mock.patch.object(odoo_sync.OdooSync, 'read')
    @mock.patch.object(odoo_sync.OdooSync, 'search')
    def test_line_payload_adjusts_accepted_invoice_discrepancy(
            self, mock_search, mock_read):
        self.conf_obj.set(
            self.cursor, self.uid, 'odoo_norma57_destination_journal', '17')
        norma57_file = mock.Mock(header_presentation_date='2026-01-15')
        line = mock.Mock(id=81, amount=-100.0, file_id=norma57_file)
        mock_search.return_value = [91]
        mock_read.return_value = {
            'odoo_last_update_result': json.dumps({'data': {'metadata': [{
                'pnt_amount_total_erp_difference': 0.01,
                'move_type': 'out_invoice',
            }]}}),
        }

        with mock.patch.object(
                self.n57_line_obj, '_get_invoice_erp_id', return_value=42):
            with mock.patch.object(self.n57_line_obj, 'browse', return_value=line):
                with mock.patch.object(
                        self.ai_obj, 'read', return_value={
                            'number': 'INV/2026/001', 'amount_total': 100.0}):
                    values = self.n57_line_obj.get_related_values(
                        self.cursor, self.uid, line.id)

        self.assertEqual(values['amount'], 100.01)

    @mock.patch.object(odoo_sync.OdooSync, 'read')
    @mock.patch.object(odoo_sync.OdooSync, 'search')
    def test_line_payload_does_not_adjust_partial_invoice_payment(
            self, mock_search, mock_read):
        self.conf_obj.set(
            self.cursor, self.uid, 'odoo_norma57_destination_journal', '17')
        norma57_file = mock.Mock(header_presentation_date='2026-01-15')
        line = mock.Mock(id=81, amount=-80.0, file_id=norma57_file)
        mock_search.return_value = [91]
        mock_read.return_value = {
            'odoo_last_update_result': json.dumps({'data': {'metadata': [{
                'pnt_amount_total_erp_difference': 0.01,
                'move_type': 'out_invoice',
            }]}}),
        }

        with mock.patch.object(
                self.n57_line_obj, '_get_invoice_erp_id', return_value=42):
            with mock.patch.object(self.n57_line_obj, 'browse', return_value=line):
                with mock.patch.object(
                        self.ai_obj, 'read', return_value={
                            'number': 'INV/2026/001', 'amount_total': 100.0}):
                    values = self.n57_line_obj.get_related_values(
                        self.cursor, self.uid, line.id)

        self.assertEqual(values['amount'], 80.0)

    def test_line_is_only_syncable_when_confirmed(self):
        line = mock.Mock(state='confirmed')

        with mock.patch.object(self.n57_line_obj, 'browse', return_value=line):
            self.assertTrue(self.n57_line_obj.check_special_restrictions(
                self.cursor, self.uid, 81))
        line.state = 'error'
        with mock.patch.object(self.n57_line_obj, 'browse', return_value=line):
            self.assertFalse(self.n57_line_obj.check_special_restrictions(
                self.cursor, self.uid, 81))

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    @mock.patch('som_sync_openerp.models.norma57_file_line.osv.osv.write')
    def test_confirming_line_triggers_automatic_sync(
            self, mock_write, mock_sync):
        mock_write.return_value = True
        with mock.patch.object(self.n57_line_obj, 'read', return_value=[{
                'id': 81,
                'state': 'draft',
        }]):
            self.n57_line_obj.write(
                self.cursor, self.uid, [81], {'state': 'confirmed'})

        mock_sync.assert_called_once_with(
            self.cursor, self.uid, 'norma57.file.line', 'write', [81], context={})

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    @mock.patch('som_sync_openerp.models.norma57_file_line.osv.osv.write')
    def test_reconfirming_line_does_not_trigger_sync(self, mock_write, mock_sync):
        mock_write.return_value = True
        with mock.patch.object(self.n57_line_obj, 'read', return_value=[{
                'id': 81,
                'state': 'confirmed',
        }]):
            self.n57_line_obj.write(
                self.cursor, self.uid, [81], {'state': 'confirmed'})

        mock_sync.assert_not_called()
