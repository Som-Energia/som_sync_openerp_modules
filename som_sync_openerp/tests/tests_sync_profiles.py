# -*- coding: utf-8 -*-
from __future__ import absolute_import

import imp
import json
import os
import xmlrpclib

import mock
from destral import testing
from osv import osv


class TestSyncProfiles(testing.OOTestCaseWithCursor):

    def setUp(self):
        super(TestSyncProfiles, self).setUp()
        self.sync = self.openerp.pool.get('odoo.sync')
        self.partner = self.openerp.pool.get('res.partner')
        self.imd = self.openerp.pool.get('ir.model.data')
        self.moves = self.openerp.pool.get('account.move')

    def mapping(self, profile, model='res.partner', erp_id=812345, **extra):
        model_id = self.openerp.pool.get('ir.model').search(
            self.cursor, self.uid, [('model', '=', model)])[0]
        vals = dict(model=model_id, res_id=erp_id, odoo_id=42,
                    sync_profile=profile, sync_state='error')
        vals.update(extra)
        return self.sync.create(self.cursor, self.uid, vals)

    def partner_id(self):
        return self.imd.get_object_reference(
            self.cursor, self.uid, 'base', 'res_partner_agrolait')[1]

    def account_id(self, code):
        account_type = self.imd.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'financieras')[1]
        with mock.patch.object(self.sync, 'common_sync_model_create_update'):
            return self.openerp.pool.get('account.account').create(self.cursor, self.uid, {
                'name': 'Profile test account', 'code': code,
                'type': 'other', 'user_type': account_type,
            })

    def cron_move(self, date='2026-01-15', posted=True):
        source_id = self.imd.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'account_move_001')[1]
        source = self.moves.browse(self.cursor, self.uid, source_id)
        with mock.patch.object(self.sync, 'common_sync_model_create_update'):
            move_id = self.moves.create(self.cursor, self.uid, {
                'date': date, 'journal_id': source.journal_id.id,
                'period_id': source.period_id.id, 'partner_id': source.partner_id.id,
                'line_id': [(0, 0, {
                    'name': 'Cron entry', 'account_id': line.account_id.id,
                    'partner_id': source.partner_id.id,
                    'journal_id': source.journal_id.id, 'period_id': source.period_id.id,
                    'date': date, 'debit': line.debit, 'credit': line.credit,
                }) for line in source.line_id],
            })
            if posted:
                self.moves.post(self.cursor, self.uid, [move_id])
        return move_id

    def cron_config(self, enabled=True, asynchronous=True):
        config = self.openerp.pool.get('odoo.sync.model.config')
        config_ids = config.search(self.cursor, self.uid, [
            ('model_id.model', '=', 'account.move')])
        if not enabled:
            config.unlink(self.cursor, self.uid, config_ids)
            return
        if not config_ids:
            model_id = self.openerp.pool.get('ir.model').search(
                self.cursor, self.uid, [('model', '=', 'account.move')])[0]
            config_ids = [config.create(self.cursor, self.uid, {'model_id': model_id})]
        config.write(self.cursor, self.uid, config_ids, {
            'auto_sync': False, 'async_enabled': asynchronous,
        })

    def test_only_moves_cron_inclusive_dates_and_posted_valid_entries(self):
        self.cron_config()
        self.cron_move('2026-01-09')
        start = self.cron_move('2026-01-10')
        end = self.cron_move('2026-01-15')
        self.cron_move('2026-01-16')
        invalid = self.cron_move('2026-01-12')
        self.cursor.execute(
            "UPDATE account_move_line SET state = 'draft' WHERE move_id = %s", (invalid,))
        context = {'sync_profile': 'all_in', 'from_fk_sync': True,
                   'only_moves_manual_load': True, 'only_moves_retry': True, 'lang': 'ca_ES'}
        original = context.copy()
        with mock.patch.object(self.sync, 'syncronize') as queued, \
                mock.patch.object(self.sync, 'syncronize_sync') as direct:
            summary = self.moves.cron_sync_only_moves(
                self.cursor, self.uid, '2026-01-10', '2026-01-15', context=context)
        self.assertEqual(summary['status'], 'completed')
        self.assertEqual(summary['scanned'], 3)
        self.assertEqual(summary['already_linked'], 0)
        # The invalid entry is submitted to the dispatcher, but is not queued.
        self.assertEqual(summary['submitted'], 3)
        self.assertEqual([call[0][4] for call in queued.call_args_list], [start, end])
        for call in queued.call_args_list:
            self.assertEqual(call[0][2:4], ('account.move', 'sync'))
            self.assertEqual(call[1]['context'], {
                'sync_profile': 'only_moves', 'only_moves_cron': True, 'lang': 'ca_ES'})
        self.assertEqual(context, original)
        direct.assert_not_called()

    def test_only_moves_cron_open_end_and_profile_scoped_mapping_filter(self):
        self.cron_config()
        full_only = self.cron_move('2026-01-20')
        linked = self.cron_move('2026-01-21')
        failed = self.cron_move('2026-01-22')
        self.mapping('all_in', model='account.move', erp_id=full_only, sync_state='synced')
        self.mapping('only_moves', model='account.move', erp_id=linked, sync_state='synced')
        self.mapping('only_moves', model='account.move', erp_id=failed, odoo_id=False)
        with mock.patch.object(self.sync, 'syncronize') as queued:
            summary = self.moves.cron_sync_only_moves(self.cursor, self.uid, '2026-01-20')
        self.assertIs(summary['date_to'], False)
        serialized = xmlrpclib.dumps((summary,), methodresponse=True)
        self.assertEqual(xmlrpclib.loads(serialized)[0][0], summary)
        queued_ids = [call[0][4] for call in queued.call_args_list]
        self.assertIn(full_only, queued_ids)
        self.assertIn(failed, queued_ids)
        self.assertNotIn(linked, queued_ids)

    def test_only_moves_cron_pages_past_linked_entries(self):
        self.cron_config()
        linked = self.cron_move('2026-01-20')
        first = self.cron_move('2026-01-21')
        second = self.cron_move('2026-01-22')
        self.mapping('only_moves', model='account.move', erp_id=linked, sync_state='synced')
        with mock.patch.object(self.moves, 'ONLY_MOVES_CRON_PAGE_SIZE', 1), \
                mock.patch.object(self.sync, 'syncronize') as queued:
            self.moves.cron_sync_only_moves(self.cursor, self.uid, '2026-01-20')
        queued_ids = [call[0][4] for call in queued.call_args_list]
        self.assertEqual(queued_ids[-2:], [first, second])
        self.assertNotIn(linked, queued_ids)
        self.assertEqual(len(queued_ids), len(set(queued_ids)))

    def test_only_moves_cron_synchronous_and_disabled_configuration(self):
        move_id = self.cron_move('2026-01-20')
        for enabled in (False, True):
            self.cron_config(enabled=enabled, asynchronous=False)
            with mock.patch.object(self.sync, 'syncronize') as queued, \
                    mock.patch.object(self.sync, 'syncronize_sync') as direct:
                summary = self.moves.cron_sync_only_moves(
                    self.cursor, self.uid, '2026-01-20', '2026-01-20')
            queued.assert_not_called()
            if enabled:
                self.assertEqual(summary['status'], 'completed')
                self.assertEqual(summary['scanned'], 1)
                self.assertEqual(summary['submitted'], 1)
                direct.assert_called_once_with(
                    self.cursor, self.uid, 'account.move', 'sync', move_id,
                    context={'sync_profile': 'only_moves', 'only_moves_cron': True})
            else:
                self.assertEqual(summary['status'], 'disabled')
                for counter in ('pages', 'scanned', 'already_linked', 'submitted'):
                    self.assertEqual(summary[counter], 0)
                direct.assert_not_called()

    def test_only_moves_cron_validates_dates_before_selection(self):
        with mock.patch.object(self.moves, 'search') as search:
            with self.assertRaises(TypeError):
                self.moves.cron_sync_only_moves(self.cursor, self.uid)
            for date_from, date_to in (
                    (None, None), ('', None), ('2026-1-01', None),
                    ('2026-02-30', None), ('2026-01-01', 'invalid'),
                    ('2026-01-02', '2026-01-01')):
                with self.assertRaises(osv.except_osv):
                    self.moves.cron_sync_only_moves(
                        self.cursor, self.uid, date_from, date_to)
            search.assert_not_called()

    def test_only_moves_cron_dry_run_does_not_select_or_dispatch(self):
        with mock.patch.object(self.moves, 'search') as search, \
                mock.patch.object(self.sync, 'common_sync_model_create_update') as dispatch:
            summary = self.moves.cron_sync_only_moves(
                self.cursor, self.uid, '2026-01-01', context={'is_dry_run': True})
        self.assertEqual(summary['status'], 'dry_run')
        for counter in ('pages', 'scanned', 'already_linked', 'submitted'):
            self.assertEqual(summary[counter], 0)
        search.assert_not_called()
        dispatch.assert_not_called()

    def test_only_moves_cron_logs_and_returns_paginated_summary(self):
        self.cron_config()
        linked = self.cron_move('2026-01-24')
        first = self.cron_move('2026-01-24')
        second = self.cron_move('2026-01-24')
        self.mapping('only_moves', model='account.move', erp_id=linked, sync_state='synced')
        with mock.patch.object(self.moves, 'ONLY_MOVES_CRON_PAGE_SIZE', 1), \
                mock.patch.object(self.sync, 'syncronize') as queued, \
                mock.patch('som_sync_openerp.models.account_move.time',
                           side_effect=[100, 102.3456]), \
                mock.patch('som_sync_openerp.models.account_move._logger') as logger:
            summary = self.moves.cron_sync_only_moves(
                self.cursor, self.uid, '2026-01-24', '2026-01-24')
        self.assertEqual(summary, {
            'sync_profile': 'only_moves', 'date_from': '2026-01-24',
            'date_to': '2026-01-24', 'status': 'completed',
            'pages': 3, 'scanned': 3, 'already_linked': 1, 'submitted': 2,
            'elapsed_seconds': 2.346,
        })
        self.assertEqual([call[0][4] for call in queued.call_args_list], [first, second])
        messages = [call[0][0] % call[0][1:] for call in logger.info.call_args_list]
        self.assertEqual(len(messages), 5)
        self.assertIn('started: date_from=2026-01-24 date_to=2026-01-24', messages[0])
        for page, message in enumerate(messages[1:-1], 1):
            self.assertIn('page={}'.format(page), message)
            self.assertIn('total_scanned={}'.format(page), message)
        self.assertIn('already_linked=1 candidates=0', messages[1])
        self.assertIn('finished: status=completed pages=3 scanned=3 already_linked=1 '
                      'submitted=2 elapsed_seconds=2.346', messages[-1])

    def test_only_moves_cron_empty_range_returns_and_logs_zero_summary(self):
        self.cron_config()
        with mock.patch('som_sync_openerp.models.account_move._logger') as logger, \
                mock.patch.object(self.sync, 'common_sync_model_create_update') as dispatch:
            summary = self.moves.cron_sync_only_moves(
                self.cursor, self.uid, '9999-12-31', '9999-12-31')
        self.assertEqual(summary['status'], 'completed')
        for counter in ('pages', 'scanned', 'already_linked', 'submitted'):
            self.assertEqual(summary[counter], 0)
        self.assertGreaterEqual(summary['elapsed_seconds'], 0)
        self.assertEqual(logger.info.call_count, 2)
        dispatch.assert_not_called()

    def test_only_moves_job_rechecks_mapping_without_remote_calls(self):
        self.cron_config()
        move_id = self.cron_move()
        self.mapping('all_in', model='account.move', erp_id=move_id, odoo_id=101)
        with mock.patch.object(self.sync, 'syncronize') as queued:
            self.moves.cron_sync_only_moves(
                self.cursor, self.uid, '2026-01-15', '2026-01-15')
        queued.assert_called_once()
        # Another job finishes after selection but before this job starts.
        mapping_id = self.mapping(
            'only_moves', model='account.move', erp_id=move_id,
            odoo_id=202, sync_state='synced')
        with mock.patch.object(self.sync, 'get_model_vals_to_sync') as prepare, \
                mock.patch('som_sync_openerp.models.odoo_sync.requests.get') as get, \
                mock.patch('som_sync_openerp.models.odoo_sync.requests.post') as post:
            for unused in range(2):
                result = self.sync.syncronize_sync(*queued.call_args[0], **queued.call_args[1])
                self.assertEqual(result, (202, move_id))
        prepare.assert_not_called()
        get.assert_not_called()
        post.assert_not_called()
        record = self.sync.browse(self.cursor, self.uid, mapping_id)
        self.assertEqual(record.sync_state, 'synced')
        self.assertEqual(record.odoo_id, 202)

    def test_only_moves_cron_real_request_and_repeat_run(self):
        self.cron_config(asynchronous=False)
        config = self.openerp.pool.get('res.config')
        config.set(self.cursor, self.uid, 'odoo_url_api', 'http://cron-test.invalid/api/')
        config.set(self.cursor, self.uid, 'odoo_api_key_only_moves', 'cron-key')
        move_id = self.cron_move()
        move = self.moves.browse(self.cursor, self.uid, move_id)
        self.mapping('only_moves', model='account.journal', erp_id=move.journal_id.id,
                     odoo_id=201, sync_state='static')
        self.mapping('only_moves', erp_id=move.partner_id.id,
                     odoo_id=202, sync_state='static')
        for line in move.line_id:
            self.mapping('shared', model='account.account', erp_id=line.account_id.id,
                         odoo_id=300 + line.account_id.id, sync_state='static')

        def partner_response(url, headers):
            self.assertEqual(url, 'http://cron-test.invalid/api/entities/partner/{}'.format(
                move.partner_id.id))
            self.assertEqual(headers['X-API-Key'], 'cron-key')
            body = {'success': True, 'data': {'odoo_id': 202}}
            return mock.Mock(status_code=200, text=json.dumps(body),
                             json=mock.Mock(return_value=body))

        response = {'success': True, 'data': {'odoo_id': 401}}
        with mock.patch('som_sync_openerp.models.odoo_sync.requests.get',
                        side_effect=partner_response) as get, \
                mock.patch('som_sync_openerp.models.odoo_sync.requests.post') as post:
            post.return_value.status_code = 201
            post.return_value.text = json.dumps(response)
            post.return_value.json.return_value = response
            self.moves.cron_sync_only_moves(
                self.cursor, self.uid, '2026-01-15', '2026-01-15')
            post.assert_called_once()
            self.assertEqual(post.call_args[0][0], 'http://cron-test.invalid/api/entries')
            self.assertEqual(post.call_args[1]['headers']['X-API-Key'], 'cron-key')
            payload = post.call_args[1]['json']
            self.assertEqual(payload['pnt_erp_id'], move_id)
            self.assertEqual(payload['journal_id'], 201)
            self.assertEqual(len(payload['lines']), 2)
            get_count = get.call_count
            self.moves.cron_sync_only_moves(
                self.cursor, self.uid, '2026-01-15', '2026-01-15')
            post.assert_called_once()
            self.assertEqual(get.call_count, get_count)
        mapping_ids = self.sync.search(self.cursor, self.uid, [
            ('model.model', '=', 'account.move'), ('res_id', '=', move_id),
            ('sync_profile', '=', 'only_moves')])
        self.assertEqual(len(mapping_ids), 1)
        record = self.sync.browse(self.cursor, self.uid, mapping_ids[0])
        self.assertEqual(record.odoo_id, 401)
        self.assertEqual(record.sync_state, 'synced')
        self.assertEqual(json.loads(record.odoo_last_sync_request), payload)

    def test_same_erp_partner_has_independent_profiles(self):
        full = self.mapping('all_in', odoo_id=41)
        moves = self.mapping('only_moves', odoo_id=42)
        self.sync.update_odoo_id(
            self.cursor, self.uid, 'res.partner', 812345, 43,
            context={'only_moves': True, 'sync_state': 'synced'})
        self.assertEqual(self.sync.browse(self.cursor, self.uid, full).odoo_id, 41)
        record = self.sync.browse(self.cursor, self.uid, moves)
        self.assertEqual(record.odoo_id, 43)
        self.assertEqual(record.sync_state, 'synced')
        self.assertEqual(self.sync.get_odoo_id_by_erp_id(
            self.cursor, self.uid, 'res.partner', 812345), 41)
        self.assertEqual(self.sync.get_odoo_id_by_erp_id(
            self.cursor, self.uid, 'res.partner', 812345,
            context={'only_moves': True}), 43)

    def test_account_mapping_is_shared(self):
        account_id = self.account_id('499991001')
        sync_id = self.mapping('all_in', model='account.account', erp_id=account_id)
        self.assertEqual(self.sync.browse(
            self.cursor, self.uid, sync_id).sync_profile, 'shared')
        self.sync.update_odoo_id(
            self.cursor, self.uid, 'account.account', account_id, 99,
            context={'only_moves': True, 'sync_state': 'synced'})
        for context in ({}, {'only_moves': True}, {'sync_profile': 'shared'}):
            self.assertEqual(self.sync.get_odoo_id_by_erp_id(
                self.cursor, self.uid, 'account.account', account_id,
                context=context), 99)
            self.assertEqual(self.sync.get_erp_id_by_odoo_id(
                self.cursor, self.uid, 'account.account', 99,
                context=context), account_id)

    def test_group_5_account_mappings_are_separate_per_profile(self):
        account_id = self.account_id('599991001')
        full = self.mapping('all_in', model='account.account', erp_id=account_id, odoo_id=61)
        moves = self.mapping('only_moves', model='account.account', erp_id=account_id, odoo_id=62)
        for sync_id, profile, remote_id, other_id in (
                (full, 'all_in', 61, 62), (moves, 'only_moves', 62, 61)):
            context = {'sync_profile': profile}
            self.assertEqual(self.sync.browse(
                self.cursor, self.uid, sync_id).sync_profile, profile)
            self.assertEqual(self.sync.get_odoo_id_by_erp_id(
                self.cursor, self.uid, 'account.account', account_id,
                context=context), remote_id)
            self.assertEqual(self.sync.get_erp_id_by_odoo_id(
                self.cursor, self.uid, 'account.account', remote_id,
                context=context), account_id)
            self.assertFalse(self.sync.get_erp_id_by_odoo_id(
                self.cursor, self.uid, 'account.account', other_id, context=context))
        self.sync.update_odoo_id(
            self.cursor, self.uid, 'account.account', account_id, 63,
            context={'only_moves': True, 'sync_state': 'synced'})
        self.assertEqual(self.sync.browse(self.cursor, self.uid, full).odoo_id, 61)
        self.assertEqual(self.sync.browse(self.cursor, self.uid, moves).odoo_id, 63)

    def test_group_5_account_cannot_be_explicitly_shared(self):
        account_id = self.account_id('599991002')
        with self.assertRaises(osv.except_osv):
            self.mapping('shared', model='account.account', erp_id=account_id)

    def test_static_mapping_is_scoped(self):
        for profile, remote_id in (('all_in', 61), ('only_moves', 62)):
            self.sync.get_or_create_static_odoo_id(
                self.cursor, self.uid, 'account.journal', 812345, remote_id,
                context={'sync_profile': profile})
        for profile, remote_id in (('all_in', 61), ('only_moves', 62)):
            self.assertEqual(self.sync.get_or_create_static_odoo_id(
                self.cursor, self.uid, 'account.journal', 812345,
                context={'sync_profile': profile}), remote_id)

    def test_only_moves_uses_dedicated_key(self):
        config = self.openerp.pool.get('res.config')
        values = {'odoo_url_api': 'http://odoo.test/api/v1/',
                  'odoo_api_key': 'full-key', 'odoo_api_key_only_moves': 'moves-key'}
        with mock.patch.object(config, 'get', side_effect=lambda cr, uid, key, default:
                               values.get(key, default)):
            self.assertEqual(self.sync._get_conn_params(
                self.cursor, self.uid, context={'only_moves': True}),
                ('http://odoo.test/api/v1/', 'moves-key'))
            self.assertEqual(self.sync._get_conn_params(
                self.cursor, self.uid, context={'sync_profile': 'shared'})[1], 'full-key')

    def test_missing_dedicated_key_never_falls_back(self):
        config = self.openerp.pool.get('res.config')
        with mock.patch.object(config, 'get', side_effect=lambda cr, uid, key, default:
                               False if key == 'odoo_api_key_only_moves' else 'full-key') as get:
            with self.assertRaises(osv.except_osv):
                self.sync._get_conn_params(self.cursor, self.uid, context={'only_moves': True})
            self.assertNotIn('odoo_api_key', [call[0][2] for call in get.call_args_list])

    def test_invalid_or_conflicting_profiles_are_rejected(self):
        for context in ({'sync_profile': 'typo'},
                        {'sync_profile': 'all_in', 'only_moves': True}):
            with self.assertRaises(osv.except_osv):
                self.sync._get_profile(context)
            with mock.patch.object(self.sync, 'write') as write:
                with self.assertRaises(osv.except_osv):
                    self.sync.common_sync_model_create_update(
                        self.cursor, self.uid, 'account.invoice', 'sync', 1,
                        context=context)
            write.assert_not_called()

    def test_only_moves_rejects_operational_models_and_addresses(self):
        for model in ('account.invoice', 'payment.order', 'res.partner.address'):
            with mock.patch.object(self.sync, 'syncronize') as queued, \
                    mock.patch.object(self.sync, 'syncronize_sync') as direct:
                self.assertEqual(self.sync.common_sync_model_create_update(
                    self.cursor, self.uid, model, 'sync', 1,
                    context={'only_moves': True, 'from_fk_sync': True}), (None, None))
            queued.assert_not_called()
            direct.assert_not_called()
            ids = self.sync.search(self.cursor, self.uid, [
                ('model.model', '=', model), ('res_id', '=', 1),
                ('sync_profile', '=', 'only_moves')])
            self.assertEqual(len(ids), 1)
            record = self.sync.browse(self.cursor, self.uid, ids[0])
            self.assertEqual(record.sync_state, 'error')
            self.assertFalse(record.odoo_id)
            self.assertIn('not allowed in only_moves', record.odoo_last_update_result)
            self.assertIn('from_fk_sync', record.odoo_last_update_result)

    def test_rejected_attempts_reuse_diagnostic_and_retry_stays_blocked(self):
        full = self.mapping('all_in', model='account.invoice', erp_id=812345, odoo_id=91)
        context = {'only_moves': True, 'only_moves_cron': True}
        with mock.patch.object(self.sync, 'create_odoo_record') as remote, \
                mock.patch.object(self.sync, 'syncronize') as queued:
            for unused in range(2):
                self.assertEqual(self.sync.syncronize_sync(
                    self.cursor, self.uid, 'account.invoice', 'sync', 812345,
                    context=context), (False, False))
            ids = self.sync.search(self.cursor, self.uid, [
                ('model.model', '=', 'account.invoice'), ('res_id', '=', 812345),
                ('sync_profile', '=', 'only_moves')])
            self.assertEqual(len(ids), 1)
            self.assertIn('only_moves_cron', self.sync.browse(
                self.cursor, self.uid, ids[0]).odoo_last_update_result)
            self.assertEqual(self.sync.retry_sync_record(
                self.cursor, self.uid, ids[0]), (False, False))
        remote.assert_not_called()
        queued.assert_not_called()
        self.assertEqual(self.sync.browse(self.cursor, self.uid, full).odoo_id, 91)
        self.assertEqual(self.sync.search(self.cursor, self.uid, [
            ('model.model', '=', 'account.invoice'), ('res_id', '=', 812345),
            ('sync_profile', '=', 'only_moves')]), ids)
        self.assertIn('only_moves_retry', self.sync.browse(
            self.cursor, self.uid, ids[0]).odoo_last_update_result)

    def test_rejected_batch_and_patch_attempts_are_recorded(self):
        context = {'only_moves': True}
        self.sync.common_sync_model_create_update(
            self.cursor, self.uid, 'account.invoice', 'sync', [812346, 812347],
            context=context)
        with mock.patch.object(self.sync, 'patch_odoo_record') as queued, \
                mock.patch.object(self.sync, 'update_odoo_record') as remote:
            self.sync.common_patch_odoo_record(
                self.cursor, self.uid, 'account.invoice', [812346], {}, context=context)
            self.sync.patch_odoo_record_sync(
                self.cursor, self.uid, 'account.invoice', 812347, {}, context=context)
        queued.assert_not_called()
        remote.assert_not_called()
        self.assertEqual(len(self.sync.search(self.cursor, self.uid, [
            ('model.model', '=', 'account.invoice'), ('res_id', 'in', [812346, 812347]),
            ('sync_profile', '=', 'only_moves'), ('sync_state', '=', 'error')])), 2)

    def test_shared_rejection_preserves_existing_remote_identity(self):
        sync_id = self.mapping('all_in', erp_id=812349, odoo_id=95)
        self.cursor.execute("UPDATE odoo_sync SET sync_profile = 'shared' WHERE id = %s",
                            (sync_id,))
        self.assertEqual(self.sync.syncronize_sync(
            self.cursor, self.uid, 'res.partner', 'sync', 812349,
            context={'sync_profile': 'shared'}), (False, False))
        record = self.sync.browse(self.cursor, self.uid, sync_id)
        self.assertEqual(record.odoo_id, 95)
        self.assertEqual(record.sync_state, 'error')
        self.assertIn('Only account.account', record.odoo_last_update_result)

    def test_rejected_dry_run_does_not_create_diagnostics(self):
        with mock.patch.object(self.sync, '_validate_profile_attempt') as validate:
            for method in (self.sync.common_sync_model_create_update,
                           self.sync.syncronize_sync):
                method(self.cursor, self.uid, 'account.invoice', 'sync', 812348,
                       context={'only_moves': True, 'is_dry_run': True})
            for method in (self.sync.common_patch_odoo_record,
                           self.sync.patch_odoo_record_sync):
                method(self.cursor, self.uid, 'account.invoice', 812348, {},
                       context={'only_moves': True, 'is_dry_run': True})
        validate.assert_not_called()

    def test_mapping_creation_still_rejects_forbidden_models(self):
        with self.assertRaises(osv.except_osv):
            self.mapping('only_moves', model='account.invoice')

    def test_only_moves_does_not_start_from_events_or_generic_demand(self):
        with mock.patch.object(self.sync, 'syncronize') as queued, \
                mock.patch.object(self.sync, 'syncronize_sync') as direct:
            for action in ('create', 'write', 'sync'):
                self.sync.common_sync_model_create_update(
                    self.cursor, self.uid, 'res.partner', action, 1,
                    context={'only_moves': True})
            queued.assert_not_called()
            direct.assert_not_called()

    def test_manual_load_queues_each_partner_with_saved_profile(self):
        context = {'sync_profile': 'only_moves', 'only_moves_manual_load': True}
        partner_ids = [812350, 812351]
        with mock.patch.object(self.sync, 'sync_model_enabled_amplified',
                               return_value=(True, False, True)), \
                mock.patch.object(self.sync, 'syncronize') as queued, \
                mock.patch.object(self.sync, 'syncronize_sync') as direct:
            self.assertEqual(self.sync.common_sync_model_create_update(
                self.cursor, self.uid, 'res.partner', 'sync', partner_ids,
                context=context), (None, None))
        self.assertEqual(queued.call_args_list, [
            mock.call(self.cursor, self.uid, 'res.partner', 'sync', partner_id,
                      context=context) for partner_id in partner_ids])
        direct.assert_not_called()
        self.assertEqual(context, {'sync_profile': 'only_moves',
                                   'only_moves_manual_load': True})

    def test_manual_load_respects_disabled_and_synchronous_configuration(self):
        context = {'sync_profile': 'only_moves', 'only_moves_manual_load': True}
        for configuration in ((False, False, False), (True, False, False)):
            with mock.patch.object(self.sync, 'sync_model_enabled_amplified',
                                   return_value=configuration), \
                    mock.patch.object(self.sync, 'syncronize') as queued, \
                    mock.patch.object(self.sync, 'syncronize_sync',
                                      return_value=(41, 812350)) as direct:
                result = self.sync.common_sync_model_create_update(
                    self.cursor, self.uid, 'res.partner', 'sync', 812350,
                    context=context)
            queued.assert_not_called()
            if configuration[0]:
                direct.assert_called_once_with(
                    self.cursor, self.uid, 'res.partner', 'sync', 812350, context=context)
                self.assertEqual(result, (41, 812350))
            else:
                direct.assert_not_called()
                self.assertEqual(result, (None, None))

    def test_manual_load_does_not_enable_events_patch_or_dry_runs(self):
        context = {'sync_profile': 'only_moves', 'only_moves_manual_load': True}
        with mock.patch.object(self.sync, 'syncronize') as queued, \
                mock.patch.object(self.sync, 'syncronize_sync') as direct, \
                mock.patch.object(self.sync, 'patch_odoo_record') as patch:
            for action in ('create', 'write'):
                self.sync.common_sync_model_create_update(
                    self.cursor, self.uid, 'res.partner', action, 812350, context=context)
            self.sync.common_sync_model_create_update(
                self.cursor, self.uid, 'res.partner', 'sync', 812350,
                context=dict(context, is_dry_run=True))
            self.sync.common_patch_odoo_record(
                self.cursor, self.uid, 'res.partner', [812350], {}, context=context)
        queued.assert_not_called()
        direct.assert_not_called()
        patch.assert_not_called()

    def test_manual_load_of_forbidden_model_records_its_origin(self):
        context = {'sync_profile': 'only_moves', 'only_moves_manual_load': True}
        with mock.patch.object(self.sync, 'syncronize') as queued, \
                mock.patch.object(self.sync, 'syncronize_sync') as direct:
            self.sync.common_sync_model_create_update(
                self.cursor, self.uid, 'account.invoice', 'sync', 812350,
                context=context)
        queued.assert_not_called()
        direct.assert_not_called()
        ids = self.sync.search(self.cursor, self.uid, [
            ('model.model', '=', 'account.invoice'), ('res_id', '=', 812350),
            ('sync_profile', '=', 'only_moves'), ('sync_state', '=', 'error')])
        self.assertEqual(len(ids), 1)
        self.assertIn('only_moves_manual_load', self.sync.browse(
            self.cursor, self.uid, ids[0]).odoo_last_update_result)

    def test_partner_payload_has_no_fk_or_payment_dependencies(self):
        with mock.patch.object(self.sync, 'common_sync_model_create_update') as dependency:
            values = self.sync.get_model_vals_to_sync(
                self.cursor, self.uid, 'res.partner', self.partner_id(),
                context={'only_moves': True})
            dependency.assert_not_called()
        self.assertEqual(set(values), set((
            'pnt_erp_id', 'name', 'lang', 'vat', 'is_customer', 'is_supplier',
            'is_company', 'type')))

    def test_only_moves_patch_is_deferred_without_scheduling_or_remote_calls(self):
        context = {'only_moves': True}
        with mock.patch.object(self.sync, 'patch_odoo_record') as queued, \
                mock.patch.object(self.sync, 'update_odoo_record') as remote, \
                mock.patch.object(self.sync, 'get_partner_odoo_id_by_erp_id') as identity:
            self.assertEqual(self.sync.common_patch_odoo_record(
                self.cursor, self.uid, 'res.partner', [1], {'name': 'Deferred'},
                context=context), (None, None))
            self.assertEqual(self.sync.patch_odoo_record_sync(
                self.cursor, self.uid, 'res.partner', 1, {'name': 'Deferred'},
                context=context), (False, False))
        queued.assert_not_called()
        remote.assert_not_called()
        identity.assert_not_called()

    def test_partner_identity_preserves_profile_when_refreshing_local_mapping(self):
        context = {'only_moves': True, 'from_fk_sync': True}
        with mock.patch.object(self.sync, 'get_odoo_id_by_erp_id', return_value=41), \
                mock.patch.object(self.sync, 'get_odoo_id_by_erp_id_from_odoo',
                                  return_value=(42, True)) as remote, \
                mock.patch.object(self.sync, 'update_odoo_id') as update:
            self.assertEqual(self.sync.get_partner_odoo_id_by_erp_id(
                self.cursor, self.uid, 1, context=context), 42)
            remote.assert_called_once_with(
                self.cursor, self.uid, 'res.partner', 1, return_status=True, context=context)
            self.assertTrue(update.call_args[1]['context']['only_moves'])
        self.assertEqual(context, {'only_moves': True, 'from_fk_sync': True})

    def test_retry_uses_saved_profile_and_independent_context(self):
        ids = [self.mapping('all_in'), self.mapping('only_moves')]
        context = {'only_moves': True, 'sync_profile': 'only_moves',
                   'from_fk_sync': True, 'only_moves_manual_load': True, 'odoo_id': 999}
        with mock.patch.object(self.sync, 'common_sync_model_create_update') as dispatch:
            for sync_id in ids:
                self.sync.retry_sync_record(self.cursor, self.uid, sync_id, context=context)
        first = dispatch.call_args_list[0][1]['context']
        second = dispatch.call_args_list[1][1]['context']
        self.assertEqual(first, {'sync_profile': 'all_in'})
        self.assertEqual(second, {'sync_profile': 'only_moves',
                                  'only_moves': True, 'only_moves_retry': True})
        self.assertIsNot(first, second)
        self.assertTrue(context['from_fk_sync'])
        self.assertTrue(context['only_moves_manual_load'])
        self.assertEqual(context['odoo_id'], 999)

    def test_all_in_address_lookup_cannot_pick_only_moves_partner(self):
        self.mapping('only_moves', odoo_id=99)
        self.mapping('all_in', odoo_id=41)
        addresses = self.openerp.pool.get('res.partner.address')
        address = mock.Mock(partner_id=mock.Mock(id=812345))
        with mock.patch.object(addresses, 'browse', return_value=address):
            self.assertEqual(addresses.get_endpoint_suffix(
                self.cursor, self.uid, 1), 'contact/41/invoice')

    def test_wizard_routes_mixed_profiles_without_mutating_screen_context(self):
        sync_ids = [self.mapping('all_in'), self.mapping('only_moves')]
        context = {'from_model': 'odoo.sync', 'active_ids': sync_ids}
        wizard = self.openerp.pool.get('wizard.sync.object.odoo')
        wizard_id = wizard.create(self.cursor, self.uid, {}, context=context)
        with mock.patch.object(self.sync, 'common_sync_model_create_update') as dispatch:
            wizard.action_sync(self.cursor, self.uid, [wizard_id], context=context)
        routes = [call[1]['context']['sync_profile'] for call in dispatch.call_args_list]
        self.assertEqual(routes, ['all_in', 'only_moves'])
        self.assertEqual(context, {'from_model': 'odoo.sync', 'active_ids': sync_ids})

    def test_generic_document_wizard_cannot_select_only_moves(self):
        wizard = self.openerp.pool.get('wizard.sync.object.odoo')
        context = {'from_model': 'res.partner', 'active_ids': [self.partner_id()],
                   'only_moves': True}
        wizard_id = wizard.create(self.cursor, self.uid, {}, context=context)
        with self.assertRaises(osv.except_osv):
            wizard.action_sync(self.cursor, self.uid, [wizard_id], context=context)

    def test_only_moves_tpv_is_an_entry_but_draft_moves_remain_blocked(self):
        moves = self.openerp.pool.get('account.move')
        context = {'only_moves': True}
        with mock.patch.object(moves, 'browse') as browse:
            self.assertFalse(moves.is_tpv_payment_move(
                self.cursor, self.uid, 1, context=context))
            browse.assert_not_called()
        for state, expected in (('posted', True), ('draft', False)):
            move = mock.Mock(state=state, line_id=[mock.Mock(state='valid')])
            with mock.patch.object(moves, 'browse', return_value=move):
                self.assertEqual(moves.check_special_restrictions(
                    self.cursor, self.uid, 1, context=context), expected)

    def test_only_moves_tpv_request_uses_real_profile_scoped_dependencies(self):
        config = self.openerp.pool.get('res.config')
        config.set(self.cursor, self.uid, 'odoo_url_api', 'http://profile-test.invalid/api/')
        config.set(self.cursor, self.uid, 'odoo_api_key', 'full-key')
        config.set(self.cursor, self.uid, 'odoo_api_key_only_moves', 'moves-key')
        sync_config = self.openerp.pool.get('odoo.sync.model.config')
        config_ids = sync_config.search(self.cursor, self.uid, [
            ('model_id.model', 'in', ['account.move', 'account.account', 'res.partner'])])
        sync_config.write(self.cursor, self.uid, config_ids, {
            'auto_sync': False, 'async_enabled': False,
        })
        move_id = self.imd.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'account_move_001')[1]
        moves = self.openerp.pool.get('account.move')
        move = moves.browse(self.cursor, self.uid, move_id)
        journal_id = move.journal_id.id
        partner_id = move.partner_id.id
        self.openerp.pool.get('account.journal').write(
            self.cursor, self.uid, journal_id, {'name': 'TPV Triodos'})
        account_type = self.imd.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'financieras')[1]
        accounts = self.openerp.pool.get('account.account')
        group_5 = accounts.create(self.cursor, self.uid, {
            'name': 'Profile-specific TPV account', 'code': '599993001',
            'type': 'other', 'user_type': account_type,
        })
        shared = accounts.create(self.cursor, self.uid, {
            'name': 'Shared TPV counterpart', 'code': '499993001',
            'type': 'other', 'user_type': account_type,
        })
        lines = self.openerp.pool.get('account.move.line')
        for line in move.line_id:
            lines.write(self.cursor, self.uid, [line.id], {
                'account_id': group_5 if line.debit else shared,
                'partner_id': partner_id,
            })
        dependencies = (
            ('account.journal', journal_id, 10101, 20101),
            ('res.partner', partner_id, 10102, 20102),
            ('account.account', group_5, 10103, 20103),
        )
        for model, erp_id, full_id, moves_id in dependencies:
            for profile, remote_id in (('all_in', full_id), ('only_moves', moves_id)):
                self.sync.get_or_create_static_odoo_id(
                    self.cursor, self.uid, model, erp_id, remote_id,
                    context={'sync_profile': profile})
        self.mapping('shared', model='account.account', erp_id=shared,
                     odoo_id=30104, sync_state='static')
        context = {'sync_profile': 'only_moves', 'only_moves_manual_load': True}
        moves.post(self.cursor, self.uid, [move_id], context=context)
        move = moves.browse(self.cursor, self.uid, move_id)
        self.assertEqual(move.state, 'posted')
        self.assertEqual(len(move.line_id), 2)
        self.assertTrue(all(line.state == 'valid' for line in move.line_id))
        self.assertEqual(sum(line.debit - line.credit for line in move.line_id), 0)

        def partner_response(url, headers):
            self.assertEqual(url, 'http://profile-test.invalid/api/entities/partner/{}'.format(
                partner_id))
            remote_id = {'full-key': 10102, 'moves-key': 20102}[headers['X-API-Key']]
            body = {'success': True, 'data': {'odoo_id': remote_id}}
            return mock.Mock(status_code=200, text=json.dumps(body),
                             json=mock.Mock(return_value=body))

        response = {'success': True, 'data': {'odoo_id': 40105}}
        with mock.patch('som_sync_openerp.models.odoo_sync.requests.get',
                        side_effect=partner_response) as get, \
                mock.patch('som_sync_openerp.models.odoo_sync.requests.post') as post:
            post.return_value.status_code = 201
            post.return_value.json.return_value = response
            post.return_value.text = json.dumps(response)
            result = self.sync.common_sync_model_create_update(
                self.cursor, self.uid, 'account.move', 'sync', move_id, context=context)

        self.assertEqual(result, (40105, move_id))
        post.assert_called_once()
        self.assertEqual(post.call_args[0][0], 'http://profile-test.invalid/api/entries')
        self.assertEqual(post.call_args[1]['headers']['X-API-Key'], 'moves-key')
        payload = post.call_args[1]['json']
        self.assertEqual(payload['pnt_erp_id'], move_id)
        self.assertEqual(payload['journal_id'], 20101)
        self.assertEqual(len(payload['lines']), 2)
        expected_lines = [
            {'account_id': 20103, 'partner_id': 20102, 'name': 'Product A', 'debit': 1000.0},
            {'account_id': 30104, 'partner_id': 20102, 'name': 'Product A', 'credit': 1000.0},
        ]
        self.assertEqual(sorted(payload['lines'], key=lambda line: line['account_id']),
                         expected_lines)
        self.assertEqual(get.call_count, 2)
        for call in get.call_args_list:
            self.assertEqual(call[1]['headers']['X-API-Key'], 'moves-key')
        record_ids = self.sync.search(self.cursor, self.uid, [
            ('model.model', '=', 'account.move'), ('res_id', '=', move_id),
            ('sync_profile', '=', 'only_moves')])
        self.assertEqual(len(record_ids), 1)
        record = self.sync.browse(self.cursor, self.uid, record_ids[0])
        self.assertEqual(record.sync_state, 'synced')
        self.assertEqual(record.odoo_id, 40105)
        self.assertEqual(json.loads(record.odoo_last_sync_request), payload)
        for model, erp_id, full_id, unused in dependencies:
            self.assertEqual(self.sync.get_odoo_id_by_erp_id(
                self.cursor, self.uid, model, erp_id), full_id)

    def test_account_scope_uses_fixed_group_5_rule(self):
        for code, expected in (('299992001', 'shared'), ('799992001', 'shared'),
                               ('599992001', 'only_moves'), ('499992001', 'shared')):
            account_id = self.account_id(code)
            sync_id = self.mapping('only_moves', model='account.account', erp_id=account_id)
            self.assertEqual(self.sync.browse(self.cursor, self.uid, sync_id).sync_profile,
                             expected)

    def test_linked_account_cannot_cross_shared_boundary_in_either_direction(self):
        accounts = self.openerp.pool.get('account.account')
        for code, new_code, profile in (
                ('499992002', '599992002', 'shared'),
                ('599992003', '499992003', 'all_in'),
                ('599992004', '499992004', 'only_moves')):
            account_id = self.account_id(code)
            self.mapping(profile, model='account.account', erp_id=account_id,
                         odoo_id=False, sync_state='error')
            with self.assertRaises(osv.except_osv):
                accounts.write(self.cursor, self.uid, account_id, {'code': new_code})
            self.assertEqual(accounts.read(
                self.cursor, self.uid, account_id, ['code'])['code'], code)

    def test_legacy_configuration_cannot_hide_saved_account_mappings(self):
        shared = self.account_id('499992010')
        separate = self.account_id('599992011')
        self.mapping('shared', model='account.account', erp_id=shared, odoo_id=91)
        self.mapping('all_in', model='account.account', erp_id=separate, odoo_id=92)
        self.mapping('only_moves', model='account.account', erp_id=separate, odoo_id=93)
        config = self.openerp.pool.get('res.config')
        for value in ('4,2', '', False, '5'):
            config.set(self.cursor, self.uid, 'odoo_sync_excluded_account_groups', value)
            for profile, remote_id in (('all_in', 92), ('only_moves', 93)):
                context = {'sync_profile': profile}
                self.assertEqual(self.sync.get_odoo_id_by_erp_id(
                    self.cursor, self.uid, 'account.account', shared, context=context), 91)
                self.assertEqual(self.sync.get_odoo_id_by_erp_id(
                    self.cursor, self.uid, 'account.account', separate, context=context),
                    remote_id)

    def test_linked_account_can_change_group_without_changing_scope(self):
        accounts = self.openerp.pool.get('account.account')
        for code, new_code, profile in (
                ('499992005', '699992005', 'shared'),
                ('599992006', '599992016', 'only_moves')):
            account_id = self.account_id(code)
            self.mapping(profile, model='account.account', erp_id=account_id, odoo_id=97)
            accounts.write(self.cursor, self.uid, [account_id], {'code': new_code})
            self.assertEqual(self.sync.get_odoo_id_by_erp_id(
                self.cursor, self.uid, 'account.account', account_id,
                context={'sync_profile': 'only_moves'}), 97)

    def test_unlinked_account_can_cross_shared_boundary(self):
        accounts = self.openerp.pool.get('account.account')
        account_id = self.account_id('499992007')
        for code in ('599992007', '499992007'):
            accounts.write(self.cursor, self.uid, [account_id], {'code': code})
            self.assertEqual(accounts.read(
                self.cursor, self.uid, account_id, ['code'])['code'], code)

    def test_batch_code_change_is_rejected_before_any_account_is_written(self):
        accounts = self.openerp.pool.get('account.account')
        unlinked = self.account_id('499992008')
        linked = self.account_id('499992009')
        self.mapping('shared', model='account.account', erp_id=linked)
        with self.assertRaises(osv.except_osv):
            accounts.write(self.cursor, self.uid, [unlinked, linked], {'code': '599992008'})
        self.assertEqual(accounts.read(self.cursor, self.uid, unlinked, ['code'])['code'],
                         '499992008')

    def test_initial_migration_keeps_fixed_group_5_rule(self):
        group_2 = self.mapping('all_in', model='account.account',
                               erp_id=self.account_id('299992014'))
        group_5 = self.mapping('all_in', model='account.account',
                               erp_id=self.account_id('599992014'))
        self.cursor.execute("UPDATE odoo_sync SET sync_profile = 'all_in' WHERE id = %s",
                            (group_2,))
        path = os.path.join(os.path.dirname(__file__), '..', 'migrations', '5.0.25.5.0',
                            'post-0013_add_sync_profiles.py')
        migration = imp.load_source('sync_profiles_migration', path)
        with mock.patch.object(migration, 'config', mock.Mock(updating_all=True)):
            migration.up(self.cursor, '0.1')
        self.assertEqual(self.sync.browse(self.cursor, self.uid, group_2).sync_profile,
                         'shared')
        self.assertEqual(self.sync.browse(self.cursor, self.uid, group_5).sync_profile,
                         'all_in')

    def test_migration_preserves_ids_and_is_repeatable(self):
        account_id = self.account_id('499991003')
        group_5_id = self.account_id('599991003')
        account = self.mapping('shared', model='account.account', erp_id=account_id)
        group_5 = self.mapping('all_in', model='account.account', erp_id=group_5_id, odoo_id=81)
        group_5_moves = self.mapping(
            'only_moves', model='account.account', erp_id=group_5_id, odoo_id=82)
        full = self.mapping('all_in', odoo_id=71)
        moves = self.mapping('only_moves', odoo_id=72)
        self.cursor.execute("UPDATE odoo_sync SET sync_profile = 'all_in' WHERE id = %s",
                            (account,))
        path = os.path.join(os.path.dirname(__file__), '..', 'migrations', '5.0.25.5.0',
                            'post-0013_add_sync_profiles.py')
        migration = imp.load_source('sync_profiles_migration', path)
        with mock.patch.object(migration, 'config', mock.Mock(updating_all=True)):
            migration.up(self.cursor, '0.1')
            migration.up(self.cursor, '0.1')
        self.assertEqual(self.sync.read(self.cursor, self.uid, account,
                                        ['sync_profile'])['sync_profile'], 'shared')
        for sync_id, profile, remote_id in (
                (full, 'all_in', 71), (moves, 'only_moves', 72),
                (group_5, 'all_in', 81), (group_5_moves, 'only_moves', 82)):
            self.assertEqual(self.sync.read(self.cursor, self.uid, sync_id,
                                            ['sync_profile'])['sync_profile'], profile)
            values = self.sync.read(self.cursor, self.uid, sync_id, ['odoo_id', 'sync_state'])
            self.assertEqual(values, {'id': sync_id, 'odoo_id': remote_id, 'sync_state': 'error'})
