
# -*- coding: utf-8 -*-
from __future__ import absolute_import
from destral import testing
import mock
from som_sync_openerp.models import odoo_sync


class TestAccountMove(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.am_obj = self.openerp.pool.get("account.move")
        self.aml_obj = self.openerp.pool.get("account.move.line")
        self.account_obj = self.openerp.pool.get("account.account")
        self.imd_obj = self.openerp.pool.get("ir.model.data")
        self.sync_obj = self.openerp.pool.get("odoo.sync")
        super(TestAccountMove, self).setUp()

    @mock.patch.object(odoo_sync.OdooSync, "common_sync_model_create_update")
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

    @mock.patch.object(odoo_sync.OdooSync, "common_sync_model_create_update")
    def test__get_related_values_prioritizes_ref_over_name(self, mock_syncronize_sync):
        move_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_move_001"
        )[1]
        line_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_move_line_001"
        )[1]
        mock_syncronize_sync.return_value = (99, 1)

        self.aml_obj.write(self.cursor, self.uid, [line_id], {'ref': 'REF-001'})

        related_values = self.am_obj.get_related_values(
            self.cursor, self.uid, move_id
        )

        self.assertIn('REF-001', [line['name'] for line in related_values['lines']])

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

    def test__check_special_restrictions_returns_false_when_move_has_blocked_account_prefix(self):
        blocked_line = mock.Mock()
        blocked_line.account_id = mock.Mock(code='572000TEST')
        move = mock.Mock()
        move.journal_id = mock.Mock(som_sync_odoo_account_moves=True)
        move.line_id = [blocked_line]

        with mock.patch.object(self.am_obj, 'browse', return_value=move):
            is_syncrozable = self.am_obj.check_special_restrictions(
                self.cursor, self.uid, 1
            )

        self.assertFalse(is_syncrozable)

    def test__check_special_restrictions_true_when_journal_syncable_and_no_blocked_prefix(self):
        allowed_line = mock.Mock()
        allowed_line.account_id = mock.Mock(code='430000TEST')
        move = mock.Mock()
        move.journal_id = mock.Mock(som_sync_odoo_account_moves=True)
        move.line_id = [allowed_line]

        with mock.patch.object(self.am_obj, 'browse', return_value=move):
            is_syncrozable = self.am_obj.check_special_restrictions(
                self.cursor, self.uid, 1
            )

        self.assertTrue(is_syncrozable)

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
