# -*- coding: utf-8 -*-
from __future__ import absolute_import

import mock

from destral import testing


class TestNorma57File(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.imd_obj = self.openerp.pool.get('ir.model.data')
        self.conf_obj = self.openerp.pool.get('res.config')
        self.n57_obj = self.openerp.pool.get('norma57.file')
        self.ai_obj = self.openerp.pool.get('account.invoice')
        super(TestNorma57File, self).setUp()

    def _create_norma57_file(self, name='Norma57 test'):
        return self.n57_obj.create(self.cursor, self.uid, {
            'name': name,
            'header_presentation_date': '2026-01-15',
        })

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

    def test_get_bank_statement_line_values_uses_confirmed_line_identity(self):
        self.conf_obj.set(
            self.cursor, self.uid, 'odoo_norma57_destination_journal', '17')
        norma57_file = mock.Mock()
        norma57_file.header_presentation_date = '2026-01-15'
        line = mock.Mock()
        line.id = 81
        line.amount = -25.5
        line.file_id = norma57_file

        with mock.patch.object(
                self.n57_obj, '_get_line_invoice_erp_id', return_value=42):
            with mock.patch.object(
                    self.ai_obj, 'read', return_value={'number': 'INV/2026/001'}):
                values = self.n57_obj._get_bank_statement_line_values(
                    self.cursor, self.uid, line)

        self.assertEqual(values, {
            'pnt_source_model': 'norma57.file.line',
            'pnt_erp_id': 81,
            'journal_id': 17,
            'date': '2026-01-15',
            'amount': 25.5,
            'payment_ref': '[FACTURA] INV/2026/001',
        })

    def test_sync_bank_statement_lines_creates_one_line_per_confirmed_line(self):
        norma57_id = self._create_norma57_file()
        confirmed_line = mock.Mock(id=81, state='confirmed')
        ignored_line = mock.Mock(id=82, state='error')
        norma57_file = mock.Mock(lines=[confirmed_line, ignored_line])
        sync_obj = self.openerp.pool.get('odoo.sync')
        payload = {'pnt_erp_id': 81}

        with mock.patch.object(self.n57_obj, 'browse', return_value=norma57_file):
            with mock.patch.object(
                    self.n57_obj, '_get_bank_statement_line_values', return_value=payload):
                with mock.patch.object(
                        sync_obj, 'sync_bank_statement_line', return_value=91) as mock_sync:
                    result = self.n57_obj.sync_bank_statement_lines(
                        self.cursor, self.uid, norma57_id)

        self.assertTrue(result)
        mock_sync.assert_called_once_with(
            self.cursor, self.uid, 'norma57.file.line', 81, payload, context={})

    def test_confirm_triggers_bank_statement_line_sync(self):
        norma57_id = self._create_norma57_file()

        with mock.patch.object(
                self.n57_obj, 'sync_bank_statement_lines') as mock_sync:
            result = self.n57_obj.confirm(self.cursor, self.uid, norma57_id)

        self.assertTrue(result)
        mock_sync.assert_called_once_with(
            self.cursor, self.uid, norma57_id, context={})
