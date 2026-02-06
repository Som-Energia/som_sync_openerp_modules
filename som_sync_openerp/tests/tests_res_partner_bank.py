# -*- coding: utf-8 -*-
from destral import testing


class TestResPartnerBank(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.rpb_obj = self.openerp.pool.get("res.partner.bank")
        self.imd_obj = self.openerp.pool.get("ir.model.data")
        self.sync_obj = self.openerp.pool.get("odoo.sync")
        super(TestResPartnerBank, self).setUp()

    def test_get_endpoint_suffix(self):
        partner_bank_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "res_partner_bank_agrolait"
        )[1]
        odoo_partner_id = 1001

        result = self.rpb_obj.get_endpoint_suffix(self.cursor, self.uid, partner_bank_id)

        partner_bank = self.rpb_obj.browse(self.cursor, self.uid, partner_bank_id)
        expected = "{}?acc_number={}".format(odoo_partner_id, partner_bank.iban)
        self.assertEqual(result, expected)
