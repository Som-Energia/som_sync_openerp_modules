#  -*- coding: utf-8 -*-
from oorq.decorators import job
from osv import osv

from .odoo_exceptions import ForeingKeyNotAvailable


class AccountMoveLine(osv.osv):
    _name = 'account.move.line'
    _inherit = 'account.move.line'

    MAPPING_FIELDS_TO_SYNC = {
        'account_id': 'account_id',
        'partner_id': 'partner_id',
        'name': 'name',
        'ref': 'ref',
        'debit': 'debit',
        'credit': 'credit',
    }
    MAPPING_FK = {
        'account_id': 'account.account',
        'partner_id': 'res.partner',
    }
    MAPPING_CONSTANTS = {
    }

    def get_mapping_model_post(self, cr, uid, id, context=None):
        return 'bank_statement_lines'

    def hook_last_modifications(self, cr, uid, data, context=None):
        if context is None:
            context = {}
        data['name'] = data.get('ref', False) or data.get('name', '')
        data.pop('ref', False)
        return data

    def _record_id(self, record):
        return record and getattr(record, 'id', record) or False

    def _move_is_payment_owned(self, cr, uid, move, context=None):
        if context is None:
            context = {}
        for model_name in ('payment.line', 'payment.order'):
            model_obj = self.pool.get(model_name)
            if model_obj and model_obj.search(
                    cr, uid, [('payment_move_id', '=', move.id)],
                    limit=1, context=context):
                return True
        return False

    def _skip_bank_statement_line_payment_sync(self, context):
        return bool(
            context.get('skip_bank_statement_line_payment_sync')
            or context.get('norma_57_name')
        )

    def _get_reconciled_invoice(self, cr, uid, lines, context=None):
        if context is None:
            context = {}
        invoice_ids = set()
        move_ids = set([line.move_id.id for line in lines if line.move_id])
        for line in lines:
            invoice = getattr(line, 'invoice', False)
            invoice_id = self._record_id(invoice)
            if invoice_id:
                invoice_ids.add(invoice_id)

        invoice_obj = self.pool.get('account.invoice')
        if move_ids:
            invoice_ids.update(invoice_obj.search(
                cr, uid, [('move_id', 'in', list(move_ids))], context=context))
        if len(invoice_ids) != 1:
            return False
        return invoice_obj.browse(
            cr, uid, list(invoice_ids)[0], context=context)

    def _amounts_match_currency_precision(
            self, cr, uid, invoice, invoice_lines, liquidity_line):
        invoice_amount = sum([
            line.debit - line.credit for line in invoice_lines
        ])
        liquidity_amount = liquidity_line.debit - liquidity_line.credit
        if not invoice_amount or not liquidity_amount:
            return False
        currency = invoice.company_id.currency_id
        currency_obj = self.pool.get('res.currency')
        return currency_obj.is_zero(
            cr, uid, currency, invoice_amount - liquidity_amount)

    def _classify_reconciled_bank_statement_lines(
            self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        if not isinstance(ids, (list, tuple)):
            ids = [ids]
        ids = list(set(ids))
        lines = list(self.browse(cr, uid, ids, context=context))
        if not lines:
            return []

        reconcile_ids = set()
        for line in lines:
            reconcile_id = self._record_id(getattr(line, 'reconcile_id', False))
            partial_id = self._record_id(
                getattr(line, 'reconcile_partial_id', False))
            if not reconcile_id or partial_id:
                return []
            reconcile_ids.add(reconcile_id)
        if len(reconcile_ids) != 1:
            return []

        invoice = self._get_reconciled_invoice(cr, uid, lines, context=context)
        if not invoice or not invoice.move_id:
            return []
        invoice_move_id = invoice.move_id.id
        invoice_lines = [
            line for line in lines if line.move_id
            and (line.move_id.id == invoice_move_id
                 or self._record_id(getattr(line, 'invoice', False)) == invoice.id
                 )
        ]
        if not invoice_lines:
            return []

        counterpart_move_ids = set([
            line.move_id.id for line in lines
            if line.move_id and line.move_id.id != invoice_move_id
        ])
        if len(counterpart_move_ids) != 1:
            return []
        counterpart_move = self.pool.get('account.move').browse(
            cr, uid, list(counterpart_move_ids)[0], context=context)
        if self._move_is_payment_owned(
                cr, uid, counterpart_move, context=context):
            return []
        if any([
                getattr(line, 'statement_id', False)
                for line in counterpart_move.line_id]):
            return []

        liquidity_lines = [
            line for line in counterpart_move.line_id
            if line.account_id and (line.account_id.code or '').startswith('572')
            and line.debit - line.credit
            and not getattr(line, 'statement_id', False)
        ]
        if len(liquidity_lines) != 1:
            return []
        liquidity_line = liquidity_lines[0]
        if not liquidity_line.journal_id.company_bank_id:
            return []
        if not self._amounts_match_currency_precision(
                cr, uid, invoice, invoice_lines, liquidity_line):
            return []

        if self.pool.get('odoo.sync').get_odoo_id_by_erp_id(
                cr, uid, self._name, liquidity_line.id):
            return []
        return [liquidity_line.id]

    def get_sync_values(
            self, cr, uid, liquidity_line_id, context=None):
        if context is None:
            context = {}
        liquidity_line = self.browse(
            cr, uid, liquidity_line_id, context=context)
        reconcile_ids = set([
            self._record_id(line.reconcile_id)
            for line in liquidity_line.move_id.line_id
            if self._record_id(getattr(line, 'reconcile_id', False))
        ])
        if len(reconcile_ids) != 1:
            return False
        reconciled_ids = self.search(
            cr, uid, [('reconcile_id', '=', list(reconcile_ids)[0])],
            context=context)
        eligible_ids = self._classify_reconciled_bank_statement_lines(
            cr, uid, reconciled_ids, context=context)
        if liquidity_line_id not in eligible_ids:
            return False

        lines = list(self.browse(cr, uid, reconciled_ids, context=context))
        invoice = self._get_reconciled_invoice(cr, uid, lines, context=context)
        sync_obj = self.pool.get('odoo.sync')
        journal_odoo_id = sync_obj.get_odoo_id_by_erp_id(
            cr, uid, 'account.journal', liquidity_line.journal_id.id)
        if not journal_odoo_id:
            raise ForeingKeyNotAvailable(
                'account.journal,{}'.format(liquidity_line.journal_id.id))
        partner_odoo_id = sync_obj.get_partner_odoo_id_by_erp_id(
            cr, uid, invoice.partner_id.id)
        if not partner_odoo_id:
            raise ForeingKeyNotAvailable(
                'res.partner,{}'.format(invoice.partner_id.id))
        if not invoice.number:
            raise Exception('Invoice {} has no number'.format(invoice.id))

        return {
            'pnt_source_model': self._name,
            'pnt_erp_id': liquidity_line.id,
            'journal_id': journal_odoo_id,
            'date': liquidity_line.date or liquidity_line.move_id.date,
            'amount': liquidity_line.debit - liquidity_line.credit,
            'partner_id': partner_odoo_id,
            'payment_ref': '[FACTURA] {}'.format(invoice.number),
        }

    def _sync_manual_bank_statement_line(
            self, cr, uid, liquidity_line_id, context=None):
        if context is None:
            context = {}
        try:
            values = self.get_sync_values(
                cr, uid, liquidity_line_id, context=context)
        except ForeingKeyNotAvailable:
            return False
        if not values:
            return False
        odoo_id, _ = self.pool.get('odoo.sync').common_sync_model_create_update(
            cr, uid, self._name, 'sync', liquidity_line_id, context=context)
        return odoo_id

    @job(queue='sync_odoo', timeout=3600, on_commit=True)
    def sync_manual_bank_statement_line(
            self, cr, uid, liquidity_line_id, context=None):
        return self._sync_manual_bank_statement_line(
            cr, uid, liquidity_line_id, context=context)

    def _enqueue_reconciled_bank_statement_lines(
            self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        liquidity_ids = self._classify_reconciled_bank_statement_lines(
            cr, uid, ids, context=context)
        sync_obj = self.pool.get('odoo.sync')
        for liquidity_id in set(liquidity_ids):
            liquidity_line = self.browse(
                cr, uid, liquidity_id, context=context)
            if not sync_obj.get_odoo_id_by_erp_id(
                    cr, uid, 'account.journal', liquidity_line.journal_id.id):
                continue
            self.sync_manual_bank_statement_line(
                cr, uid, liquidity_id, context=context)
        return liquidity_ids

    def reconcile(self, cr, uid, ids, type='auto', writeoff_acc_id=False,
                  writeoff_period_id=False, writeoff_journal_id=False,
                  context=None):
        if context is None:
            context = {}
        result = super(AccountMoveLine, self).reconcile(
            cr, uid, ids, type=type, writeoff_acc_id=writeoff_acc_id,
            writeoff_period_id=writeoff_period_id,
            writeoff_journal_id=writeoff_journal_id, context=context)
        if self._skip_bank_statement_line_payment_sync(context):
            return result
        self._enqueue_reconciled_bank_statement_lines(
            cr, uid, ids, context=context)
        return result


AccountMoveLine()
