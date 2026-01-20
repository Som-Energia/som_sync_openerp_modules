# -*- coding: utf-8 -*-
from destral import testing


class TestResPartnerAddress(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.rp_obj = self.openerp.pool.get("res.partner.address")
        self.imd_obj = self.openerp.pool.get("ir.model.data")
        self.os_obj = self.openerp.pool.get("odoo.sync")
        super(TestResPartnerAddress, self).setUp()

    def test_get_endpoint_suffix(self):
        partner_address_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "base", "res_partner_address_8"
        )[1]
        partner_id = self.rp_obj.browse(self.cursor, self.uid, partner_address_id).partner_id.id
        context = {
            'sync_state': 'synced',
        }
        odoo_partner_id = 4001
        self.os_obj.update_odoo_id(
            self.cursor, self.uid, "res.partner", partner_id, odoo_partner_id, context)
        suffix = self.rp_obj.get_endpoint_suffix(self.cursor, self.uid, partner_address_id)
        self.assertEqual(suffix, "contact/4001/invoice")
