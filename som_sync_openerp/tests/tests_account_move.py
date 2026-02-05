
# -*- coding: utf-8 -*-
from destral import testing
from mock import MagicMock


class TestAccountMove(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.am_obj = self.openerp.pool.get("account.move")
        self.imd_obj = self.openerp.pool.get("ir.model.data")
        self.sync_obj = self.openerp.pool.get("odoo.sync")
        super(TestAccountMove, self).setUp()

    def test__get_related_values(self):
        move_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_move_001"
        )[1]
        self.sync_obj.syncronize_sync = MagicMock(
            return_value=(99, 1))

        related_values = self.am_obj.get_related_values(
            self.cursor, self.uid, move_id
        )

        expected_values = {
            'lines': [
                {
                    'account_id': 99,
                    'credit': 1000.0,
                    'name': u'Product A',
                    'partner_id': 99,
                },
                {
                    'account_id': 99,
                    'debit': 1000.0,
                    'name': u'Product A',
                    'partner_id': 99,
                }
            ]

        }
        self.assertEqual(related_values, expected_values)

    def test__journal_is_syncrozable_True(self):
        move_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_move_001"
        )[1]

        is_syncrozable = self.am_obj._journal_is_syncrozable(
            self.cursor, self.uid, move_id
        )

        self.assertTrue(is_syncrozable)

    def test__journal_is_syncrozable_False(self):
        move_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_move_002"
        )[1]

        is_syncrozable = self.am_obj._journal_is_syncrozable(
            self.cursor, self.uid, move_id
        )

        self.assertFalse(is_syncrozable)

    def test__write_triggers_async(self):
        move_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_move_001"
        )[1]
        # sync_model_enabled_amplified returns (sync_enabled, auto_sync, async_enabled)
        self.sync_obj.sync_model_enabled_amplified = MagicMock(
            return_value=(True, True, True))
        self.sync_obj.syncronize = MagicMock()

        # Perform write operation
        self.am_obj.write(
            self.cursor,
            self.uid,
            [move_id],
            {'state': 'posted'},
        )

        self.sync_obj.syncronize.assert_called_once()

    def test__write_no_triggers_async_journal_disabled_sync(self):
        move_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_move_002"
        )[1]
        # sync_model_enabled_amplified returns (sync_enabled, auto_sync, async_enabled)
        self.sync_obj.sync_model_enabled_amplified = MagicMock(
            return_value=(True, True, True))
        self.sync_obj.syncronize = MagicMock()

        # Perform write operation
        self.am_obj.write(
            self.cursor,
            self.uid,
            [move_id],
            {'state': 'posted'},
        )

        self.sync_obj.syncronize.assert_not_called()

    def test__write__autosync_not_enabled_no_trigger(self):
        move_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_move_001"
        )[1]
        # sync_model_enabled_amplified returns (sync_enabled, auto_sync, async_enabled)
        self.sync_obj.sync_model_enabled_amplified = MagicMock(
            return_value=(True, False, False))
        self.sync_obj.syncronize = MagicMock()
        self.sync_obj.syncronize_sync = MagicMock()

        # Perform write operation on a field that does not trigger sync
        self.am_obj.write(
            self.cursor,
            self.uid,
            [move_id],
            {'state': 'posted'},
        )

        # Assert that the sync method was not called
        self.sync_obj.syncronize.assert_not_called()
        self.sync_obj.syncronize_sync.assert_not_called()
