
# -*- coding: utf-8 -*-
from destral import testing


class TestAccountMove(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.am_obj = self.openerp.pool.get("account.move")
        self.imd_obj = self.openerp.pool.get("ir.model.data")
        super(TestAccountMove, self).setUp()

    def test__journal_is_syncrozable_True(self):
        move_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_move_001"
        )[1]

        is_syncrozable = self.am_obj._journal_is_syncrozable(
            self.cursor, self.uid, [move_id]
        )

        self.assertTrue(is_syncrozable)

    def test__journal_is_syncrozable_False(self):
        move_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_move_002"
        )[1]

        is_syncrozable = self.am_obj._journal_is_syncrozable(
            self.cursor, self.uid, [move_id]
        )

        self.assertFalse(is_syncrozable)
