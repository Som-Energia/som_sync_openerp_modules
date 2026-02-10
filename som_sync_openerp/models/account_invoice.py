#  -*- coding: utf-8 -*-
from osv import osv


class AccountInvoice(osv.osv):
    _name = 'account.invoice'
    _inherit = 'account.invoice'

    MAPPING_FIELDS_TO_SYNC = {
        "id": "pnt_erp_id",
        "number": "number",
        "partner_id": "partner_id",
        "journal_id": "journal_id",
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
        'journal_id': 'account.journal',
        "payment_term": "account.payment.term",
        "payment_type": "payment.type",
        "fiscal_position": "account.fiscal.position",
    }
    MAPPING_CONSTANTS = {
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

        # Add tax lines needed for the sync with Odoo
        res.extend(self.add_taxes_lines_needed_for_sync(cr, uid, id, context=context))

        return {
            'date': account_invoice.date_invoice,
            'invoice_line_ids': res
        }

    def _journal_is_syncrozable(self, cr, uid, _id, context=None):
        invoice = self.browse(cr, uid, _id, context=context)
        return invoice.journal_id and invoice.journal_id.som_sync_odoo_invoices

    def write(self, cr, uid, ids, vals, context=None):
        if context is None:
            context = {}
        if not isinstance(ids, list):
            ids = [ids]

        res = super(AccountInvoice, self).write(cr, uid, ids, vals, context=context)

        for _id in ids:
            if self._journal_is_syncrozable(cr, uid, _id, context=context) and \
                'state' in vals and \
                    vals['state'] == 'open':
                sync_obj = self.pool.get('odoo.sync')
                sync_obj.common_sync_model_create_update(
                    cr, uid, self._name, _id, 'create', context=context
                )

        return res

    def add_taxes_lines_needed_for_sync(self, cr, uid, invoice_id, context=None):
        """
        This method is called from account.invoice to add the tax lines
        needed for the sync with Odoo.
        Lines to add if we have IESE tax lines:
        * Extra line 1:
            - quantity = 1
            - price_unit = amount of the tax IESE line
        * Extra line 2:
            - quantity = 1
            - price_unit = amount base of the tax IESE line
        * Extra line 3:
            - quantity = -1
            - price_unit = amount base general
        """
        if context is None:
            context = {}
        tax_line_obj = self.pool.get('account.invoice.tax')
        tax_line_ids = tax_line_obj.search(
            cr, uid, [('invoice_id', '=', invoice_id)], context=context)
        amount_untaxed = self.read(cr, uid, invoice_id, ['amount_untaxed'])['amount_untaxed']
        res = []
        for tax_line in tax_line_obj.browse(cr, uid, tax_line_ids, context=context):
            if 'Impuesto especial' in tax_line.name:
                res = [
                    {
                        'name': 'Import IESE',
                        'quantity': 1,
                        'price_unit': tax_line.amount,
                    }, {
                        'name': 'Base IESE',
                        'quantity': 1,
                        'price_unit': tax_line.base_amount,
                    }, {
                        'name': 'Base general',
                        'quantity': -1,
                        'price_unit': amount_untaxed,
                    }
                ]
                break

        return res


AccountInvoice()
