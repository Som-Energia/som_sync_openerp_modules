#  -*- coding: utf-8 -*-
from datetime import datetime
import logging
from time import time

from osv import osv
from service.security import Sudo
from base_extended_som.utils import is_dry_run


_logger = logging.getLogger(__name__)


class AccountMove(osv.osv):
    _name = 'account.move'
    _inherit = 'account.move'

    SYNC_BLOCKED_ACCOUNT_PREFIXES = ('572',)
    TPV_JOURNAL_NAME = 'tpv triodos'
    ONLY_MOVES_CRON_PAGE_SIZE = 1000

    MAPPING_FIELDS_TO_SYNC = {
        'id': 'pnt_erp_id',
        'name': 'number',
        'journal_id': 'journal_id',
        'ref': 'ref',
        'date': 'date',
    }
    MAPPING_FK = {
        'journal_id': 'account.journal',
    }
    MAPPING_CONSTANTS = {
    }

    def get_related_values(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        account_move = self.browse(cr, uid, id, context=context)
        if self.is_tpv_payment_move(cr, uid, id, context=context):
            return self._get_tpv_statement_values(cr, uid, account_move, context=context)
        res = []
        sync_obj = self.pool.get('odoo.sync')
        for line in account_move.line_id:
            if line.debit == 0 and line.credit == 0:
                continue
            aml_vals = sync_obj.get_model_vals_to_sync(
                cr, uid, 'account.move.line', line.id, context=context)
            if aml_vals['debit'] == 0:
                # remove the item from the dictionary
                aml_vals.pop('debit')
            if aml_vals['credit'] == 0:
                # remove the item from the dictionary
                aml_vals.pop('credit')
            res.append(aml_vals)
        if not res:
            raise ValueError('Cannot synchronize an entry with no nonzero journal lines')
        return {'lines': res}

    def is_tpv_payment_move(self, cr, uid, id, context=None):
        if (context or {}).get('only_moves') or \
                (context or {}).get('sync_profile') == 'only_moves':
            return False
        move = self.browse(cr, uid, id, context=context)
        return move.journal_id and \
            move.journal_id.name.strip().lower() == self.TPV_JOURNAL_NAME

    def get_mapping_model_post(self, cr, uid, id, context=None):
        if self.is_tpv_payment_move(cr, uid, id, context=context):
            return 'bank_statement_lines'
        return 'entries'

    def hook_last_modifications(self, cr, uid, data, context=None):
        if data.get('pnt_source_model') == 'account.move':
            # The statement endpoint rejects generic journal-entry fields.
            data.pop('number', None)
            data.pop('ref', None)
        return data

    def _get_tpv_statement_values(self, cr, uid, move, context=None):
        invoice_obj = self.pool.get('account.invoice')
        sync_obj = self.pool.get('odoo.sync')
        receivable_lines = [line for line in move.line_id
                            if line.account_id.type == 'receivable']
        if len(move.line_id) != 2 or len(receivable_lines) != 1 or \
                any(line.state != 'valid' for line in move.line_id):
            raise ValueError('TPV synchronization requires a valid two-line collection')
        payment_line = receivable_lines[0]
        if not payment_line.reconcile_id:
            raise ValueError('TPV collection must be fully reconciled before synchronization')
        invoice_ids = list(set(invoice_obj._get_invoice_from_line(
            cr, uid, [payment_line.id], context=context)))
        if len(invoice_ids) != 1:
            raise ValueError('TPV collection must be linked to exactly one invoice')
        invoice = invoice_obj.browse(cr, uid, invoice_ids[0], context=context)
        amount = round(payment_line.credit - payment_line.debit, 2)
        if invoice.type != 'out_invoice' or invoice.state != 'paid' or \
                invoice.group_move_id or not invoice.number or amount <= 0 or \
                round(amount - invoice.amount_total, 2) != 0:
            raise ValueError('Only full, individual customer invoice TPV collections are supported')
        if invoice.currency_id.id != invoice.company_id.currency_id.id:
            raise ValueError('Foreign-currency TPV collections are not supported')

        previous_sync_ids = sync_obj.search(cr, uid, sync_obj._mapping_domain(
            cr, uid, self._name, move.id, context), limit=1)
        if previous_sync_ids:
            previous = sync_obj.read(cr, uid, previous_sync_ids[0], [
                'odoo_id', 'odoo_last_sync_endpoint',
            ])
            if previous['odoo_id'] and \
                    (previous['odoo_last_sync_endpoint'] or '').rstrip('/').endswith('/entries'):
                raise ValueError(
                    'TPV move was already exported as an entry; manual review required')

        dependency_context = dict(context or {}, from_fk_sync=True)
        odoo_invoice_id, _ = sync_obj.common_sync_model_create_update(
            cr, uid, 'account.invoice', 'sync', invoice.id, context=dependency_context)
        if not odoo_invoice_id:
            raise ValueError('TPV invoice must be synchronized with Odoo first')
        # FK retries can return a saved Odoo ID even when invoice validation failed.
        accepted_invoice_sync_ids = sync_obj.search(cr, uid, sync_obj._mapping_domain(
            cr, uid, 'account.invoice', invoice.id, context) + [
            ('odoo_id', '=', odoo_invoice_id),
            ('sync_state', 'in', ['synced', 'synced_with_warning', 'static']),
        ], limit=1)
        if not accepted_invoice_sync_ids:
            raise ValueError('TPV invoice synchronization must be successful before collection')
        invoice_sync = sync_obj.read(cr, uid, accepted_invoice_sync_ids[0], [
            'odoo_last_update_result',
        ])
        difference, _ = invoice_obj._get_total_amount_difference(invoice_sync)
        # Keep ERP validation above, but match Odoo's accepted invoice balance.
        if difference:
            amount = round(amount + difference, 2)
        partner_id = sync_obj.get_partner_odoo_id_by_erp_id(cr, uid, invoice.partner_id.id)
        if not partner_id:
            partner_id, _ = sync_obj.common_sync_model_create_update(
                cr, uid, 'res.partner', 'sync', invoice.partner_id.id,
                context=dependency_context)
        if not partner_id:
            raise ValueError('TPV invoice partner has no Odoo mapping')
        return {
            'pnt_source_model': self._name,
            'amount': amount,
            'payment_ref': '[FACTURA] {}'.format(invoice.number),
            'partner_id': partner_id,
        }

    def check_special_restrictions(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        if context.get('only_moves') or context.get('sync_profile') == 'only_moves':
            move = self.browse(cr, uid, id, context=context)
            return move.state == 'posted' and bool(move.line_id) and all(
                line.state == 'valid' for line in move.line_id)
        if not self._journal_is_syncrozable(cr, uid, id, context=context):
            return False
        if self.is_tpv_payment_move(cr, uid, id, context=context):
            move = self.browse(cr, uid, id, context=context)
            return bool(move.line_id) and all(line.state == 'valid' for line in move.line_id)
        return not self._has_blocked_account_prefix(cr, uid, id, context=context)

    def _journal_is_syncrozable(self, cr, uid, _id, context=None):
        move = self.browse(cr, uid, _id, context=context)
        return move.journal_id and move.journal_id.som_sync_odoo_account_moves

    def _has_blocked_account_prefix(self, cr, uid, _id, context=None):
        if context is None:
            context = {}
        move = self.browse(cr, uid, _id, context=context)
        for line in move.line_id:
            account_code = line.account_id and line.account_id.code or ''
            if any(account_code.startswith(prefix)
                   for prefix in self.SYNC_BLOCKED_ACCOUNT_PREFIXES):
                return True
        return False

    def cron_sync_only_moves(self, cr, uid, date_from, date_to=None, context=None):
        """Dispatch unlinked posted entries within inclusive accounting dates."""
        try:
            for value in ([date_from, date_to] if date_to is not None else [date_from]):
                if datetime.strptime(value, '%Y-%m-%d').strftime('%Y-%m-%d') != value:
                    raise ValueError()
        except (TypeError, ValueError):
            raise osv.except_osv('Invalid date range', 'Dates must use YYYY-MM-DD format.')
        if date_to is not None and date_to < date_from:
            raise osv.except_osv('Invalid date range', 'date_to must not precede date_from.')
        started_at = time()
        summary = {
            'sync_profile': 'only_moves', 'date_from': date_from,
            'date_to': date_to if date_to is not None else False,
            'status': 'completed', 'pages': 0, 'scanned': 0,
            'already_linked': 0, 'submitted': 0,
        }
        _logger.info('only_moves cron started: date_from=%s date_to=%s',
                     date_from, date_to or 'open')

        if is_dry_run(context):
            summary['status'] = 'dry_run'
        else:
            sync = self.pool.get('odoo.sync')
            cron_context = sync._clean_context_update_data(cr, uid, context)
            for flag in ('from_fk_sync', 'only_moves', 'only_moves_retry',
                         'only_moves_manual_load', 'is_static'):
                cron_context.pop(flag, None)
            cron_context.update(sync_profile='only_moves', only_moves_cron=True)
            if not sync.sync_model_enabled_amplified(cr, uid, self._name)[0]:
                summary['status'] = 'disabled'

        if summary['status'] == 'completed':
            domain = [('state', '=', 'posted'), ('date', '>=', date_from)]
            if date_to is not None:
                domain.append(('date', '<=', date_to))
            last_id = 0
            while True:
                move_ids = self.search(
                    cr, uid, domain + [('id', '>', last_id)],
                    order='id', limit=self.ONLY_MOVES_CRON_PAGE_SIZE, context=cron_context)
                if not move_ids:
                    break
                last_id = move_ids[-1]
                mapping_ids = sync.search(cr, uid, [
                    ('model.model', '=', self._name), ('res_id', 'in', move_ids),
                    ('sync_profile', '=', 'only_moves'), ('odoo_id', '>', 0),
                ], context=cron_context)
                linked_ids = set(record['res_id'] for record in sync.read(
                    cr, uid, mapping_ids, ['res_id'], context=cron_context))
                pending_ids = [move_id for move_id in move_ids if move_id not in linked_ids]
                summary['pages'] += 1
                summary['scanned'] += len(move_ids)
                summary['already_linked'] += len(linked_ids)
                _logger.info(
                    'only_moves cron page=%s last_id=%s scanned=%s already_linked=%s '
                    'candidates=%s total_scanned=%s',
                    summary['pages'], last_id, len(move_ids), len(linked_ids),
                    len(pending_ids), summary['scanned'])
                if pending_ids:
                    sync.common_sync_model_create_update(
                        cr, uid, self._name, 'sync', pending_ids, context=cron_context)
                    summary['submitted'] += len(pending_ids)

        summary['elapsed_seconds'] = round(time() - started_at, 3)
        _logger.info(
            'only_moves cron finished: status=%s pages=%s scanned=%s already_linked=%s '
            'submitted=%s elapsed_seconds=%s',
            summary['status'], summary['pages'], summary['scanned'],
            summary['already_linked'], summary['submitted'], summary['elapsed_seconds'])
        return summary

    def post(self, cr, uid, ids, context=None):
        if context is None:
            context = {}

        res = super(AccountMove, self).post(cr, uid, ids, context=context)

        if context.get('invoice'):
            return res

        self._sync_posted_moves(cr, uid, ids, context=context)

        return res

    def write(self, cr, uid, ids, vals, context=None):
        if context is None:
            context = {}
        if not isinstance(ids, list):
            ids = [ids]

        res = super(AccountMove, self).write(cr, uid, ids, vals, context=context)

        if 'state' in vals and vals['state'] == 'posted':
            self._sync_posted_moves(cr, uid, ids, context=context)

        return res

    def _sync_posted_moves(self, cr, uid, ids, context=None):
        if not isinstance(ids, (list, tuple)):
            ids = [ids]
        if (context or {}).get('defer_tpv_payment_sync'):
            ids = [id for id in ids
                   if not self.is_tpv_payment_move(cr, uid, id, context=context)]
        if ids:
            with Sudo(uid=1, gid=0):
                self.pool.get('odoo.sync').common_sync_model_create_update(
                    cr, uid, self._name, 'create', ids, context=context)


AccountMove()
