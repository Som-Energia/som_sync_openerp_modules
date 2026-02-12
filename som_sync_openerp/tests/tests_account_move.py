
# -*- coding: utf-8 -*-
from __future__ import absolute_import
from destral import testing
import mock
from som_sync_openerp.models import odoo_sync


class TestAccountMove(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.am_obj = self.openerp.pool.get("account.move")
        self.imd_obj = self.openerp.pool.get("ir.model.data")
        self.sync_obj = self.openerp.pool.get("odoo.sync")
        super(TestAccountMove, self).setUp()

    @mock.patch.object(odoo_sync.OdooSync, "syncronize_sync")
    def test__get_related_values(self, mock_syncronize_sync):
        move_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_move_001"
        )[1]
        mock_syncronize_sync.return_value = (99, 1)

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

    @mock.patch.object(odoo_sync.OdooSync, "syncronize_sync")
    @mock.patch.object(odoo_sync.OdooSync, "sync_model_enabled_amplified")
    def test__write_triggers_async(self, mock_sync_model_enabled_amplified, mock_syncronize_sync):
        move_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_move_001"
        )[1]
        mock_sync_model_enabled_amplified.return_value = (True, True, True)

        # Perform write operation
        self.am_obj.write(
            self.cursor,
            self.uid,
            [move_id],
            {'state': 'posted'},
        )

        mock_syncronize_sync.assert_called_once()

    @mock.patch.object(odoo_sync.OdooSync, "syncronize_sync")
    @mock.patch.object(odoo_sync.OdooSync, "sync_model_enabled_amplified")
    def test__write_no_triggers_async_journal_disabled_sync(
            self, mock_sync_model_enabled_amplified, mock_syncronize_sync):
        move_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_move_002"
        )[1]
        mock_sync_model_enabled_amplified.return_value = (True, True, True)

        # Perform write operation
        self.am_obj.write(
            self.cursor,
            self.uid,
            [move_id],
            {'state': 'posted'},
        )

        mock_syncronize_sync.assert_not_called()

    @mock.patch.object(odoo_sync.OdooSync, "syncronize_sync")
    @mock.patch.object(odoo_sync.OdooSync, "sync_model_enabled_amplified")
    def test__write__autosync_not_enabled_no_trigger(
            self, mock_sync_model_enabled_amplified, mock_syncronize_sync):
        move_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_move_001"
        )[1]
        mock_sync_model_enabled_amplified.return_value = (True, False, False)

        # Perform write operation on a field that does not trigger sync
        self.am_obj.write(
            self.cursor,
            self.uid,
            [move_id],
            {'state': 'posted'},
        )

        # Assert that the sync method was not called
        mock_syncronize_sync.assert_not_called()
        mock_syncronize_sync.assert_not_called()
