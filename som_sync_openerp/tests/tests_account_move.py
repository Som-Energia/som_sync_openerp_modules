
# -*- coding: utf-8 -*-
from __future__ import absolute_import
from destral import testing
import mock
import requests
from osv import osv
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
    def test_write_prevents_synced_move_from_returning_to_draft(self, mock_sync):
        move_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_move_001"
        )[1]
        model_id = self.openerp.pool.get('ir.model').search(
            self.cursor, self.uid, [('model', '=', 'account.move')], limit=1
        )[0]
        self.am_obj.write(self.cursor, self.uid, [move_id], {'state': 'posted'})
        self.sync_obj.create(self.cursor, self.uid, {
            'model': model_id,
            'res_id': move_id,
            'sync_state': 'synced',
        })

        with self.assertRaises(Exception) as error:
            self.am_obj.write(self.cursor, self.uid, [move_id], {'state': 'draft'})

        self.assertIn('synchronized journal entry', str(error.exception))
        self.assertEqual(
            self.am_obj.read(self.cursor, self.uid, move_id, ['state'])['state'],
            'posted',
        )

    @mock.patch.object(odoo_sync.OdooSync, "common_sync_model_create_update")
    @mock.patch.object(odoo_sync.OdooSync, "sync_model_enabled_amplified")
    @mock.patch.object(odoo_sync.OdooSync, "get_model_vals_to_sync")
    @mock.patch('som_sync_openerp.models.odoo_sync.requests.post')
    def test_failed_retry_keeps_move_protected(
            self, mock_post, mock_vals, mock_enabled, mock_sync):
        move_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_move_001"
        )[1]
        self.am_obj.write(self.cursor, self.uid, [move_id], {'state': 'posted'})
        self.sync_obj.update_odoo_id(
            self.cursor, self.uid, 'account.move', move_id, 99,
            context={'sync_state': 'synced'})
        mock_enabled.return_value = (True, False, False)
        mock_vals.return_value = {'pnt_erp_id': move_id}
        mock_post.side_effect = requests.exceptions.ConnectionError('Odoo unavailable')

        self.sync_obj.syncronize_sync(
            self.cursor, self.uid, 'account.move', 'sync', move_id)

        mock_post.assert_called_once()
        sync_ids = self.sync_obj.search(self.cursor, self.uid, [
            ('model.model', '=', 'account.move'), ('res_id', '=', move_id),
        ])
        sync_record = self.sync_obj.read(
            self.cursor, self.uid, sync_ids[0], ['sync_state', 'odoo_id'])
        self.assertEqual(sync_record['sync_state'], 'error')
        self.assertEqual(sync_record['odoo_id'], 99)
        with self.assertRaises(osv.except_osv) as error:
            self.am_obj.write(self.cursor, self.uid, [move_id], {'state': 'draft'})
        self.assertIn('synchronized journal entry', str(error.exception))
        self.assertEqual(
            self.am_obj.read(self.cursor, self.uid, move_id, ['state'])['state'],
            'posted')

    @mock.patch.object(odoo_sync.OdooSync, "common_sync_model_create_update")
    def test_write_prevents_move_with_odoo_id_and_error_from_returning_to_draft(
            self, mock_sync):
        move_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_move_001"
        )[1]
        self.am_obj.write(self.cursor, self.uid, [move_id], {'state': 'posted'})
        self.sync_obj.update_odoo_id(
            self.cursor, self.uid, 'account.move', move_id, 99,
            context={'sync_state': 'error'})

        with self.assertRaises(osv.except_osv) as error:
            self.am_obj.write(self.cursor, self.uid, [move_id], {'state': 'draft'})
        self.assertIn('synchronized journal entry', str(error.exception))
        self.assertEqual(
            self.am_obj.read(self.cursor, self.uid, move_id, ['state'])['state'],
            'posted')

    @mock.patch.object(odoo_sync.OdooSync, "common_sync_model_create_update")
    def test_write_allows_move_without_odoo_id_after_failed_sync(self, mock_sync):
        move_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_move_001"
        )[1]
        self.am_obj.write(self.cursor, self.uid, [move_id], {'state': 'posted'})
        self.sync_obj.update_odoo_id(
            self.cursor, self.uid, 'account.move', move_id, False,
            context={'sync_state': 'error'})

        self.am_obj.write(self.cursor, self.uid, [move_id], {'state': 'draft'})

        self.assertEqual(
            self.am_obj.read(self.cursor, self.uid, move_id, ['state'])['state'],
            'draft')

    @mock.patch.object(odoo_sync.OdooSync, "common_sync_model_create_update")
    @mock.patch.object(odoo_sync.OdooSync, "get_partner_odoo_id_by_erp_id")
    def test__get_related_values(self, mock_partner_odoo_id, mock_syncronize_sync):
        move_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_move_001"
        )[1]
        mock_syncronize_sync.return_value = (99, 1)
        mock_partner_odoo_id.return_value = False

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
    @mock.patch.object(odoo_sync.OdooSync, "get_partner_odoo_id_by_erp_id")
    def test__get_related_values_prioritizes_ref_over_name(
            self, mock_partner_odoo_id, mock_syncronize_sync):
        move_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_move_001"
        )[1]
        line_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_move_line_001"
        )[1]
        mock_syncronize_sync.return_value = (99, 1)
        mock_partner_odoo_id.return_value = False

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

    @mock.patch.object(odoo_sync.OdooSync, "syncronize")
    @mock.patch.object(odoo_sync.OdooSync, "sync_model_enabled_amplified")
    def test__post_triggers_sync(
            self, mock_sync_model_enabled_amplified, mock_syncronize):
        move_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_move_001"
        )[1]
        mock_sync_model_enabled_amplified.return_value = (True, True, True)

        self.am_obj.post(self.cursor, self.uid, [move_id])

        mock_syncronize.assert_called_once_with(
            self.cursor, self.uid, 'account.move', 'create', move_id, context={}
        )

    @mock.patch.object(odoo_sync.OdooSync, "syncronize")
    @mock.patch.object(odoo_sync.OdooSync, "sync_model_enabled_amplified")
    def test__post_does_not_sync_when_journal_is_not_enabled(
            self, mock_sync_model_enabled_amplified, mock_syncronize):
        move_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_move_002"
        )[1]
        mock_sync_model_enabled_amplified.return_value = (True, True, True)

        self.am_obj.post(self.cursor, self.uid, [move_id])

        mock_syncronize.assert_not_called()

    @mock.patch.object(odoo_sync.OdooSync, "common_sync_model_create_update")
    def test__post_does_not_sync_invoice_move(self, mock_sync_create_update):
        move_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_move_001"
        )[1]

        self.am_obj.post(self.cursor, self.uid, [move_id], context={'invoice': True})

        mock_sync_create_update.assert_not_called()

    @mock.patch.object(odoo_sync.OdooSync, "syncronize")
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
