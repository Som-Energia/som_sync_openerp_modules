#  -*- coding: utf-8 -*-
from osv import osv
from service.security import Sudo


class AccountMove(osv.osv):
    _name = 'account.move'
    _inherit = 'account.move'

    SYNC_BLOCKED_ACCOUNT_PREFIXES = ('572',)
    TPV_JOURNAL_NAME = 'tpv triodos'

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
            aml_vals = sync_obj.get_model_vals_to_sync(
                cr, uid, 'account.move.line', line.id, context=context)
            if aml_vals['debit'] == 0:
                # remove the item from the dictionary
                aml_vals.pop('debit')
            if aml_vals['credit'] == 0:
                # remove the item from the dictionary
                aml_vals.pop('credit')
            res.append(aml_vals)
        return {'lines': res}

    def is_tpv_payment_move(self, cr, uid, id, context=None):
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

        previous_sync_ids = sync_obj.search(cr, uid, [
            ('model.model', '=', self._name), ('res_id', '=', move.id),
        ], limit=1)
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
