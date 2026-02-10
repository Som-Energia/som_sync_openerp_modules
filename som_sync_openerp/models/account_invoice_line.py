#  -*- coding: utf-8 -*-
from osv import osv


class AccountInvoiceLine(osv.osv):
    _name = 'account.invoice.line'
    _inherit = 'account.invoice.line'

    MAPPING_FIELDS_TO_SYNC = {
        'name': 'name',
        'quantity': 'quantity',
        'price_unit': 'price_unit',
        'account_id': 'account_id',
        'invoice_line_tax_id': 'tax_ids',
    }
    MAPPING_FK = {
        'account_id': 'account.account',
        'tax_id': 'account.tax',
    }
    MAPPING_CONSTANTS = {
        'extra_operations_erp': 1,
    }

    def get_related_values(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        account_invoice_line = self.browse(cr, uid, id, context=context)
        tax_ids = []
        if account_invoice_line.invoice_line_tax_id:
            tax_ids = [tax.id for tax in account_invoice_line.invoice_line_tax_id]
        res = {
            'quantity_erp': account_invoice_line.quantity,
            'tax_ids': tax_ids,
        }
        return res


AccountInvoiceLine()
