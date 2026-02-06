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
        "invoice_date": "invoice_date",
        "amount_untaxed": "amount_untaxed",
        "amount_tax": "amount_tax",
        "amount_total": "amount_total",
        "type": "move_type",
        "date": "date",
        "invoice_payment_term_id": "invoice_payment_term_id",
        "preferred_payment_method_line_id": "preferred_payment_method_line_id",
        "fiscal_position_id": "fiscal_position_id",
    }
    MAPPING_FK = {
        "partner_id": "res.partner",
        # 'journal_id': 'account.journal',
        "invoice_payment_term_id": "account.payment.term",
        "preferred_payment_method_line_id": "account.payment.method",
        "fiscal_position_id": "account.fiscal.position",
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
        return {'invoice_line_ids': res}

    def _journal_is_syncrozable(self, cr, uid, _id, context=None):
        invoice = self.browse(cr, uid, _id, context=context)
        return invoice.journal_id and invoice.journal_id.som_sync_odoo_invoices

    # def write(self, cr, uid, ids, vals, context=None):
    #     if context is None:
    #         context = {}
    #     if not isinstance(ids, list):
    #         ids = [ids]

    #     res = super(AccountInvoice, self).write(cr, uid, ids, vals, context=context)

    #     for _id in ids:
    #         if self._journal_is_syncrozable(cr, uid, _id, context=context) and \
    #             'state' in vals and \
    #                 vals['state'] == 'posted':
    #             sync_obj = self.pool.get('odoo.sync')
    #             sync_obj.common_sync_model_create_update(
    #                 cr, uid, self._name, _id, 'create', context=context
    #             )

    #     return res


AccountInvoice()
