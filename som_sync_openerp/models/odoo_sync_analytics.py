# -*- coding: utf-8 -*-
from __future__ import absolute_import

from datetime import datetime
import logging

import requests
from oorq.decorators import job
from oorq.oorq import AsyncMode
from osv import osv
from service.security import Sudo
from base_extended_som.utils import is_dry_run, skip_job_in_dry_run


class OdooSyncAnalytics(osv.osv):
    _name = 'odoo.sync'
    _inherit = 'odoo.sync'

    def _entry_analytics_path(self, record):
        return 'entries/{}/analytics'.format(record.res_id)

    def _is_entry_analytics_mapping(self, record):
        endpoint = (record.odoo_last_sync_endpoint or '').rstrip('/')
        return (record.model.model == 'account.move' and record.odoo_id > 0
                and record.sync_profile in ('all_in', 'only_moves')
                and (endpoint.endswith('/entries') or endpoint == 'entries'
                     or endpoint.endswith(self._entry_analytics_path(record))))

    def _write_entry_analytics_log(self, cursor, uid, sync_id, values):
        values = dict(values, odoo_last_sync_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        with Sudo(uid=1, gid=0):
            self.write(cursor, uid, [sync_id], values)

    def enqueue_entry_analytics(self, cursor, uid, move_id, context=None):
        """Queue each existing entry export, never create or infer item links."""
        if is_dry_run(context) or not self.sync_model_enabled_amplified(
                cursor, uid, 'account.move')[0]:
            return
        ids = self.search(cursor, uid, [
            ('model.model', '=', 'account.move'), ('res_id', '=', move_id),
            ('odoo_id', '>', 0), ('sync_profile', 'in', ['all_in', 'only_moves']),
        ])
        for record in self.browse(cursor, uid, ids):
            if self._is_entry_analytics_mapping(record):
                self._write_entry_analytics_log(cursor, uid, record.id, {
                    'sync_state': 'pending',
                    'odoo_last_sync_endpoint': self._entry_analytics_path(record),
                    'odoo_last_sync_request': False,
                    'odoo_last_update_result': False,
                })
                with AsyncMode('async'):
                    self.sync_entry_analytics(cursor, uid, record.id)

    @skip_job_in_dry_run
    @job(queue='sync_odoo', timeout=3600, on_commit=True)
    def sync_entry_analytics(self, cursor, uid, sync_id, context=None):
        self.sync_entry_analytics_sync(cursor, uid, sync_id, context=context)

    def sync_entry_analytics_sync(self, cursor, uid, sync_id, context=None):
        if is_dry_run(context):
            return False
        record = self.browse(cursor, uid, sync_id)
        if not self._is_entry_analytics_mapping(record):
            return False
        # Serialize jobs and concurrent analytic edits; always send current data,
        # not a wizard snapshot that another queued reassignment can supersede.
        cursor.execute(
            'SELECT id FROM account_move_line WHERE move_id = %s ORDER BY id FOR UPDATE',
            (record.res_id,))
        cursor.fetchall()
        values = {'sync_state': 'error', 'odoo_last_sync_request': False,
                  'odoo_last_sync_endpoint': self._entry_analytics_path(record)}
        try:
            if not self.sync_model_enabled_amplified(cursor, uid, 'account.move')[0]:
                raise ValueError('Journal entry synchronization is disabled.')
            profile_context = {'sync_profile': record.sync_profile}
            move = self.pool.get('account.move')._check_analytic_reassignment(
                cursor, uid, record.res_id, context=profile_context)
            lines = []
            for line in move.line_id:
                if not line.debit and not line.credit:
                    continue  # Entry POSTs omit these items too.
                analytic_id = None
                if line.analytic_account_id:
                    analytic_id = self.get_odoo_id_by_erp_id(
                        cursor, uid, 'account.analytic.account',
                        line.analytic_account_id.id, context=profile_context)
                    if not analytic_id:
                        raise ValueError(
                            'No {} Odoo mapping for analytic account {}.'.format(
                                record.sync_profile, line.analytic_account_id.id))
                if line.analytics_id:
                    raise ValueError('Analytic distributions require manual review.')
                lines.append({'pnt_erp_id': line.id, 'analytic_account_id': analytic_id})
            if not lines:
                raise ValueError('The entry has no exported journal items.')
            payload = {'lines': lines}
            values['odoo_last_sync_request'] = self.format_response(payload)
            base, api_key = self._get_conn_params(cursor, uid, context=profile_context)
            base = base.rstrip('/')
            if base.endswith('/api'):
                base += '/v1'
            endpoint = '{}/{}'.format(base, self._entry_analytics_path(record))
            values['odoo_last_sync_endpoint'] = endpoint
            response = requests.patch(
                endpoint, json=payload,
                headers={'X-API-Key': api_key, 'Accept': 'application/json'},
                timeout=30)
            values['odoo_last_update_result'] = response.text
            data = response.json()
            if response.status_code == 200 and isinstance(data, dict) and \
                    data.get('success') is True:
                values['sync_state'] = 'synced'
        except Exception as error:
            logging.getLogger('openerp.odoo.sync').exception(
                'Failed analytic PATCH for synchronization %s', sync_id)
            values['odoo_last_update_result'] = str(error)
        self._write_entry_analytics_log(cursor, uid, sync_id, values)
        return values['sync_state'] == 'synced'

    def retry_sync_record(self, cursor, uid, sync_id, context=None):
        record = self.browse(cursor, uid, sync_id)
        if (self._is_entry_analytics_mapping(record)
                and (record.odoo_last_sync_endpoint or '').rstrip('/').endswith(
                    self._entry_analytics_path(record))):
            if not is_dry_run(context):
                with AsyncMode('async'):
                    self.sync_entry_analytics(cursor, uid, sync_id)
            return None, None
        return super(OdooSyncAnalytics, self).retry_sync_record(
            cursor, uid, sync_id, context=context)


OdooSyncAnalytics()
