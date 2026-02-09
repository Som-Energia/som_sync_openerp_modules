#  -*- coding: utf-8 -*-
from osv import osv


class AccountInvoice(osv.osv):
    _name = 'account.invoice'
    _inherit = 'account.invoice'

    MAPPING_FIELDS_TO_SYNC = {
        "id": "pnt_erp_id",
        "number": "number",
        "partner_id": "partner_id",
        # "journal_id": "journal_id",
        "date_invoice": "invoice_date",
        "amount_untaxed": "amount_untaxed",
        "amount_tax": "amount_tax",
        "amount_total": "amount_total",
        "type": "move_type",
        "payment_term": "invoice_payment_term_id",
        "payment_type": "preferred_payment_method_line_id",
        "fiscal_position": "fiscal_position_id",
    }
    MAPPING_FK = {
        "partner_id": "res.partner",
        # 'journal_id': 'account.journal',
        "payment_term": "account.payment.term",
        "payment_type": "payment.type",
        "fiscal_position": "account.fiscal.position",
    }
    MAPPING_CONSTANTS = {
        'journal_id': 8,  # so far fixed as sales journal 'Factures de client'
    }

    def get_related_values(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        account_invoice = self.browse(cr, uid, id, context=context)
        res = []
        for line in account_invoice.invoice_line:
            sync_obj = self.pool.get('odoo.sync')
            ail_vals = sync_obj.get_model_vals_to_sync(
                cr, uid, 'account.invoice.line', line.id, context=context)
            res.append(ail_vals)
        return {
            'date': account_invoice.date_invoice,
            'invoice_line_ids': res
        }

    def check_special_restrictions(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        return self._journal_is_syncrozable(cr, uid, id, context=context)

    def _journal_is_syncrozable(self, cr, uid, _id, context=None):
        invoice = self.browse(cr, uid, _id, context=context)
        return invoice.journal_id and invoice.journal_id.som_sync_odoo_invoices

    def write(self, cr, uid, ids, vals, context=None):
        if context is None:
            context = {}
        if not isinstance(ids, list):
            ids = [ids]

        res = super(AccountInvoice, self).write(cr, uid, ids, vals, context=context)

        if 'state' in vals and vals['state'] == 'open':
            sync_obj = self.pool.get('odoo.sync')
            sync_obj.common_sync_model_create_update(
                cr, uid, self._name, ids, 'create', context=context
            )

        return res


AccountInvoice()
