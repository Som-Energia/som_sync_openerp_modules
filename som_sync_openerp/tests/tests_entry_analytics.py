# -*- coding: utf-8 -*-
from __future__ import absolute_import

import json
import mock
from destral import testing
from osv import osv

from som_sync_openerp.models import odoo_sync_analytics


class TestEntryAnalytics(testing.OOTestCaseWithCursor):
    def setUp(self):
        super(TestEntryAnalytics, self).setUp()
        self.sync = self.openerp.pool.get('odoo.sync')
        self.moves = self.openerp.pool.get('account.move')
        self.lines = self.openerp.pool.get('account.move.line')
        imd = self.openerp.pool.get('ir.model.data')
        self.move_id = imd.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'account_move_001')[1]
        with mock.patch.object(self.sync, 'common_sync_model_create_update'):
            self.moves.post(self.cursor, self.uid, [self.move_id])
        move = self.moves.browse(self.cursor, self.uid, self.move_id)
        self.line_ids = sorted(line.id for line in move.line_id)
        analytic_journal = self.openerp.pool.get('account.analytic.journal').create(
            self.cursor, self.uid, {'name': 'Sync analytics', 'code': 'SYN', 'type': 'general'})
        self.openerp.pool.get('account.journal').write(
            self.cursor, self.uid, [move.journal_id.id],
            {'analytic_journal_id': analytic_journal})
        self.analytic_id = self.openerp.pool.get('account.analytic.account').create(
            self.cursor, self.uid, {'name': 'Entry analytics'})
        defaults = self.openerp.pool.get('account.analytic.default')
        defaults.unlink(self.cursor, self.uid, defaults.search(self.cursor, self.uid, []))

    def mapping(self, profile='only_moves', endpoint='http://odoo/api/v1/entries',
                model='account.move', erp_id=None, odoo_id=123):
        model_id = self.openerp.pool.get('ir.model').search(
            self.cursor, self.uid, [('model', '=', model)])[0]
        return self.sync.create(self.cursor, self.uid, {
            'model': model_id, 'res_id': erp_id or self.move_id,
            'odoo_id': odoo_id, 'sync_profile': profile, 'sync_state': 'synced',
            'odoo_last_sync_endpoint': endpoint,
        })

    def apply(self, analytic_id):
        return self.moves.apply_analytic_assignments(
            self.cursor, self.uid, self.move_id,
            dict((line_id, analytic_id) for line_id in self.line_ids))

    def state(self, sync_id):
        return self.sync.read(self.cursor, self.uid, sync_id, [
            'sync_state', 'odoo_last_sync_endpoint', 'odoo_last_sync_request',
            'odoo_last_update_result', 'odoo_id'])

    def run_patch(self, sync_id, status=200, body=None):
        response = mock.Mock(status_code=status)
        body = body if body is not None else {'success': True}
        response.text = json.dumps(body)
        response.json.return_value = body
        with mock.patch.object(
                self.sync, '_get_conn_params', return_value=('http://odoo/api/', 'only-key')
        ), mock.patch.object(
                odoo_sync_analytics.requests, 'patch', return_value=response) as patch:
            result = self.sync.sync_entry_analytics_sync(
                self.cursor, self.uid, sync_id, context={'sync_profile': 'all_in'})
        return result, patch

    def test_hook_queues_both_export_profiles_after_local_write(self):
        records = [self.mapping(profile) for profile in ('all_in', 'only_moves')]
        with mock.patch.object(self.sync, 'sync_entry_analytics') as queued:
            self.assertTrue(self.apply(self.analytic_id))
        self.assertItemsEqual([call[0][2] for call in queued.call_args_list], records)
        for sync_id in records:
            self.assertEqual(self.state(sync_id)['sync_state'], 'pending')
        for line in self.lines.browse(self.cursor, self.uid, self.line_ids):
            self.assertEqual(line.analytic_account_id.id, self.analytic_id)

    def test_confirmation_queues_even_if_unchanged_but_invalid_choices_do_not(self):
        self.mapping()
        with mock.patch.object(self.sync, 'sync_entry_analytics') as queued:
            self.apply(False)
            with self.assertRaises(osv.except_osv):
                self.moves.apply_analytic_assignments(
                    self.cursor, self.uid, self.move_id, {})
        queued.assert_called_once()

    def test_enqueue_forces_async_even_when_caller_is_synchronous(self):
        self.mapping()
        mode = odoo_sync_analytics.AsyncMode
        with mode('sync'), mock.patch.object(
                self.sync, 'sync_entry_analytics',
                side_effect=lambda *args: self.assertTrue(mode.is_async())) as queued:
            self.apply(self.analytic_id)
            self.assertFalse(mode.is_async())
        queued.assert_called_once()

    def test_unexported_or_statement_entries_are_local_only(self):
        with mock.patch.object(self.sync, 'sync_entry_analytics') as queued:
            self.apply(self.analytic_id)
            self.mapping(endpoint='http://odoo/api/v1/bank_statement_lines')
            self.apply(False)
        queued.assert_not_called()

    def test_disabled_and_dry_run_do_not_queue(self):
        self.mapping()
        with mock.patch.object(self.sync, 'sync_entry_analytics') as queued:
            self.sync.enqueue_entry_analytics(
                self.cursor, self.uid, self.move_id, context={'is_dry_run': True})
            with mock.patch.object(
                    self.sync, 'sync_model_enabled_amplified', return_value=(False, False, False)):
                self.apply(self.analytic_id)
        queued.assert_not_called()

    def test_patch_uses_current_values_profile_mapping_and_explicit_null(self):
        sync_id = self.mapping()
        self.mapping('all_in', model='account.analytic.account',
                     erp_id=self.analytic_id, odoo_id=888)
        self.mapping('only_moves', model='account.analytic.account',
                     erp_id=self.analytic_id, odoo_id=999)
        with mock.patch.object(self.sync, 'sync_entry_analytics'):
            self.apply(self.analytic_id)
            self.lines.write(self.cursor, self.uid, [self.line_ids[1]],
                             {'analytic_account_id': False})
        defaults = self.openerp.pool.get('account.analytic.default')
        with mock.patch.object(defaults, 'account_get') as lookup:
            result, patch = self.run_patch(sync_id)
        lookup.assert_not_called()
        self.assertTrue(result)
        args, kwargs = patch.call_args
        self.assertEqual(args, ('http://odoo/api/v1/entries/{}/analytics'.format(self.move_id),))
        self.assertItemsEqual(kwargs['json']['lines'], [
            {'pnt_erp_id': self.line_ids[1], 'analytic_account_id': None},
            {'pnt_erp_id': self.line_ids[0], 'analytic_account_id': 999},
        ])
        self.assertEqual(kwargs['headers']['X-API-Key'], 'only-key')
        self.assertEqual(kwargs['timeout'], 30)
        self.assertEqual(self.state(sync_id)['sync_state'], 'synced')

    def test_missing_profile_analytic_mapping_blocks_whole_patch(self):
        sync_id = self.mapping()
        self.mapping('all_in', model='account.analytic.account',
                     erp_id=self.analytic_id, odoo_id=888)
        with mock.patch.object(self.sync, 'sync_entry_analytics'):
            self.apply(self.analytic_id)
        result, patch = self.run_patch(sync_id)
        self.assertFalse(result)
        patch.assert_not_called()
        self.assertIn('No only_moves Odoo mapping', self.state(sync_id)['odoo_last_update_result'])

    def test_legacy_missing_item_ids_remain_error_without_post_or_backfill(self):
        sync_id = self.mapping()
        self.mapping(model='account.analytic.account',
                     erp_id=self.analytic_id, odoo_id=999)
        with mock.patch.object(self.sync, 'sync_entry_analytics'):
            self.apply(self.analytic_id)
        with mock.patch.object(odoo_sync_analytics.requests, 'post') as post:
            result, _ = self.run_patch(sync_id, 400, {'success': False, 'message': 'Unknown item'})
        self.assertFalse(result)
        post.assert_not_called()
        self.assertEqual(self.state(sync_id)['odoo_id'], 123)
        self.assertEqual(self.state(sync_id)['sync_state'], 'error')
        for line in self.lines.browse(self.cursor, self.uid, self.line_ids):
            self.assertEqual(line.analytic_account_id.id, self.analytic_id)

    def test_transport_failure_retains_patch_retry_routing(self):
        sync_id = self.mapping()
        with mock.patch.object(
                self.sync, '_get_conn_params', return_value=('http://odoo/api/v1/', 'k')), \
                mock.patch.object(odoo_sync_analytics.requests, 'patch',
                                  side_effect=odoo_sync_analytics.requests.Timeout('Timed out')):
            self.assertFalse(self.sync.sync_entry_analytics_sync(
                self.cursor, self.uid, sync_id))
        self.assertIn('Timed out', self.state(sync_id)['odoo_last_update_result'])
        with mock.patch.object(self.sync, 'sync_entry_analytics') as queued, \
                mock.patch.object(self.sync, 'common_sync_model_create_update') as create:
            self.sync.retry_sync_record(
                self.cursor, self.uid, sync_id, context={'sync_profile': 'all_in'})
        queued.assert_called_once_with(self.cursor, self.uid, sync_id)
        create.assert_not_called()

    def test_profile_connection_is_taken_from_saved_mapping(self):
        sync_id = self.mapping()
        with mock.patch.object(
                self.sync, '_get_conn_params', side_effect=ValueError('No key')) as conn:
            self.assertFalse(self.sync.sync_entry_analytics_sync(
                self.cursor, self.uid, sync_id, context={'sync_profile': 'all_in'}))
        conn.assert_called_once_with(
            self.cursor, self.uid, context={'sync_profile': 'only_moves'})

    def test_invalid_json_is_recorded_as_error(self):
        sync_id = self.mapping()
        response = mock.Mock(status_code=200, text='not JSON')
        response.json.side_effect = ValueError('Invalid JSON')
        with mock.patch.object(
                self.sync, '_get_conn_params', return_value=('http://odoo/api/v1/', 'k')), \
                mock.patch.object(odoo_sync_analytics.requests, 'patch', return_value=response):
            self.assertFalse(self.sync.sync_entry_analytics_sync(self.cursor, self.uid, sync_id))
        self.assertEqual(self.state(sync_id)['sync_state'], 'error')

    def test_patch_response_is_pretty_printed_for_success_and_errors(self):
        sync_id = self.mapping()
        for status, body in (
                (200, {'success': True, 'data': {'name': u'Caf\u00e9'}}),
                (400, {'success': False, 'message': u'Invalid account: Caf\u00e9'})):
            result, _ = self.run_patch(sync_id, status, body)
            self.assertEqual(result, status == 200)
            self.assertEqual(
                self.state(sync_id)['odoo_last_update_result'],
                json.dumps(body, ensure_ascii=False, indent=2))

    def test_post_item_id_mapping_applies_to_both_profiles(self):
        self.assertEqual(self.lines.MAPPING_FIELDS_TO_SYNC['id'], 'pnt_erp_id')
        self.assertEqual(self.lines.ONLY_MOVES_FIELDS_TO_SYNC['id'], 'pnt_erp_id')

    def test_local_default_is_resolved_before_queueing(self):
        self.mapping()
        move = self.moves.browse(self.cursor, self.uid, self.move_id)
        self.openerp.pool.get('account.analytic.default').create(self.cursor, self.uid, {
            'account_id': move.line_id[0].account_id.id, 'analytic_id': self.analytic_id,
            'date_start': move.line_id[0].date, 'date_stop': move.line_id[0].date,
        })
        with mock.patch.object(self.sync, 'sync_entry_analytics') as queued:
            self.apply(False)
        queued.assert_called_once()
        line = self.lines.browse(self.cursor, self.uid, move.line_id[0].id)
        self.assertEqual(line.analytic_account_id.id, self.analytic_id)
