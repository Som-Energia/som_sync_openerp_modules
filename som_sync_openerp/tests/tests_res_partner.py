# -*- coding: utf-8 -*-
from destral import testing
from ..models import odoo_sync
import mock


class TestResPartner(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.rp_obj = self.openerp.pool.get("res.partner")
        self.imd_obj = self.openerp.pool.get("ir.model.data")
        super(TestResPartner, self).setUp()

    def test_get_endpoint_suffix(self):
        partner_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "base", "res_partner_agrolait"
        )[1]

        suffix = self.rp_obj.get_endpoint_suffix(self.cursor, self.uid, partner_id)

        self.assertEqual(suffix, 'company/ES72789709E')

    @mock.patch.object(odoo_sync.OdooSync, "common_sync_model_create_update")
    def test__get_related_values(self, mock_syncronize_sync):
        partner_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "base", "res_partner_agrolait"
        )[1]
        mock_syncronize_sync.return_value = (99, 1)

        related_values = self.rp_obj.get_related_values(
            self.cursor, self.uid, partner_id
        )

        expected_values = {
            'property_outbound_payment_method_line_id': 375  # Transferencias APi
        }
        self.assertEqual(related_values, expected_values)
