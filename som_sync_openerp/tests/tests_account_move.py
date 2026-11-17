
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

    @mock.patch.object(odoo_sync.OdooSync, "common_sync_model_create_update")
    @mock.patch.object(odoo_sync.OdooSync, "get_partner_odoo_id_by_erp_id")
    def test_zero_amount_lines_are_skipped_in_both_profiles(
            self, mock_partner_odoo_id, mock_sync):
        move_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'account_move_001')[1]
        move = self.am_obj.browse(self.cursor, self.uid, move_id)
        source = move.line_id[0]
        zero_id = self.aml_obj.create(self.cursor, self.uid, {
            'move_id': move_id, 'name': 'Zero amount',
            'account_id': source.account_id.id,
            'partner_id': source.partner_id.id,
            'journal_id': move.journal_id.id, 'period_id': move.period_id.id,
            'debit': 0, 'credit': 0,
        })
        nonzero_ids = [line.id for line in move.line_id if line.id != zero_id]
        # Small nonzero amounts must not be treated as zero.
        for line in move.line_id:
            if line.id != zero_id:
                self.aml_obj.write(self.cursor, self.uid, [line.id], {
                    'debit': 0.01 if line.debit else 0,
                    'credit': 0.01 if line.credit else 0,
                })
        mock_sync.return_value = (99, 1)
        mock_partner_odoo_id.return_value = False
        for profile in ('all_in', 'only_moves'):
            context = {'sync_profile': profile}
            with mock.patch.object(
                    self.sync_obj, 'get_model_vals_to_sync',
                    wraps=self.sync_obj.get_model_vals_to_sync) as prepare:
                result = self.am_obj.get_related_values(
                    self.cursor, self.uid, move_id, context=context)
            self.assertEqual(sorted(call[0][3] for call in prepare.call_args_list),
                             sorted(nonzero_ids))
            self.assertEqual(len(result['lines']), 2)
            self.assertEqual(sum(line.get('debit', 0) for line in result['lines']), 0.01)
            self.assertEqual(sum(line.get('credit', 0) for line in result['lines']), 0.01)
            self.assertTrue(all(('debit' in line) != ('credit' in line)
                                for line in result['lines']))

    def test_all_zero_lines_are_rejected_before_dependencies_in_both_profiles(self):
        move_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'account_move_001')[1]
        move = self.am_obj.browse(self.cursor, self.uid, move_id)
        self.aml_obj.write(self.cursor, self.uid, [line.id for line in move.line_id], {
            'debit': 0, 'credit': 0,
        })
        for profile in ('all_in', 'only_moves'):
            with mock.patch.object(self.sync_obj, 'get_model_vals_to_sync') as prepare:
                with self.assertRaisesRegexp(ValueError, 'no nonzero journal lines'):
                    self.am_obj.get_related_values(
                        self.cursor, self.uid, move_id,
                        context={'sync_profile': profile})
            prepare.assert_not_called()

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
