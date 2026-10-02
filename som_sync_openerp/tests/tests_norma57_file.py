# -*- coding: utf-8 -*-
from __future__ import absolute_import

import mock

from destral import testing


class TestNorma57File(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.conf_obj = self.openerp.pool.get('res.config')
        self.n57_obj = self.openerp.pool.get('norma57.file')
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
                        self.ai_obj, 'read', return_value={'number': 'INV/2026/001'}):
                    values = self.n57_line_obj.get_related_values(
                        self.cursor, self.uid, line.id)

        self.assertEqual(values, {
            'journal_id': 17,
            'date': '2026-01-15',
            'amount': 25.5,
            'payment_ref': '[FACTURA] INV/2026/001',
        })

    def test_line_is_only_syncable_when_confirmed(self):
        line = mock.Mock(state='confirmed')

        with mock.patch.object(self.n57_line_obj, 'browse', return_value=line):
            self.assertTrue(self.n57_line_obj.check_special_restrictions(
                self.cursor, self.uid, 81))
        line.state = 'error'
        with mock.patch.object(self.n57_line_obj, 'browse', return_value=line):
            self.assertFalse(self.n57_line_obj.check_special_restrictions(
                self.cursor, self.uid, 81))
