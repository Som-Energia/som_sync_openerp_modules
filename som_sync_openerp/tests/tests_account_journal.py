# -*- coding: utf-8 -*-
from __future__ import absolute_import

from destral import testing


class TestAccountJournal(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.aj_obj = self.openerp.pool.get("account.journal")
        self.imd_obj = self.openerp.pool.get("ir.model.data")
        super(TestAccountJournal, self).setUp()

    def test__company_bank_id_must_be_unique(self):
        bank_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "base", "res_partner_bank_0001"
        )[1]
        view_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "account", "account_journal_view"
        )[1]
        sequence_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "account", "sequence_journal"
        )[1]

        with self.assertRaises(Exception):
            self.aj_obj.create(self.cursor, self.uid, {
                'name': 'Duplicate bank journal',
                'code': 'DupBank',
                'type': 'general',
                'company_bank_id': bank_id,
                'view_id': view_id,
                'sequence_id': sequence_id,
            })
