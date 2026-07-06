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
        super(TestNorma57File, self).setUp()

    def _create_norma57_file(self, name='Norma57 test'):
        return self.n57_obj.create(self.cursor, self.uid, {
            'name': name,
            'header_presentation_date': '2026-01-15',
        })

    def _build_mock_line(self, invoice_id, amount=100.0, state='confirmed'):
        line = mock.Mock()
        line.state = state
        line.amount = amount
        line.resource = 'account.invoice,{}'.format(invoice_id)
        return line

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

        with mock.patch.object(type(self.ai_obj), 'process_lines_with_discrepancies') as mock_discrepancies:  # noqa: E501
            with mock.patch.object(self.n57_obj, 'browse') as mock_browse:
                norma57_file = mock.Mock()
                norma57_file.name = 'Norma57 test'
                norma57_file.lines = [mock_line]
                mock_browse.return_value = norma57_file
                related_values = self.n57_obj.get_related_values(self.cursor, self.uid, norma57_id)

        self.assertEqual(related_values, {
            'destination_journal_id': 17,
            'payment_method_line_id': 411,
            'name': 'Norma57 test',
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

    def test_get_line_invoice_erp_id_uses_invoice_id_from_related_model(self):
        line = mock.Mock()
        line.resource = 'fake.model,7'
        related_obj = mock.Mock()
        related_obj.read.return_value = {'invoice_id': (42, 'INV/42')}

        with mock.patch.object(self.n57_obj.pool, 'get', return_value=related_obj) as mock_get:
            invoice_id = self.n57_obj._get_line_invoice_erp_id(self.cursor, self.uid, line)

        self.assertEqual(invoice_id, 42)
        mock_get.assert_called_once_with('fake.model')
        related_obj.read.assert_called_once_with(
            self.cursor, self.uid, 7, ['invoice_id'], context={}
        )

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
                norma57_file.lines = [mock_line]
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
