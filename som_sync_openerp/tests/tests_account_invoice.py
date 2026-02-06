
# -*- coding: utf-8 -*-
from destral import testing
from mock import patch
from ..models import odoo_sync


class TestAccountInvoice(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.ai_obj = self.openerp.pool.get("account.invoice")
        self.imd_obj = self.openerp.pool.get("ir.model.data")
        self.sync_obj = self.openerp.pool.get("odoo.sync")
        super(TestAccountInvoice, self).setUp()

    @patch.object(odoo_sync.OdooSync, "syncronize_sync")
    def test__get_related_values(self, mock_syncronize_sync):
        move_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "invoice_0001"
        )[1]
        mock_syncronize_sync.return_value = (99, 1)

        related_values = self.ai_obj.get_related_values(
            self.cursor, self.uid, move_id
        )

        expected_values = {
            'invoice_line_ids': [
                {
                    'account_id': 99,
                    'name': u'Product A',
                    'price_unit': 1000.0,
                    'quantity': 1.0,
                    'quantity_erp': 1.0
                }
            ]
        }
        self.assertEqual(related_values, expected_values)
