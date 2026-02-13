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
        "reference": "ref",
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

    def check_special_restrictions(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        return self._journal_is_syncrozable(cr, uid, id, context=context) and \
            self._is_invoice_syncrozable(cr, uid, id, context)

    def _journal_is_syncrozable(self, cr, uid, _id, context=None):
        invoice = self.browse(cr, uid, _id, context=context)
        return invoice.journal_id and invoice.journal_id.som_sync_odoo_invoices

    def _is_invoice_syncrozable(self, cr, uid, id, context=None):
        return self.read(cr, uid, id, ['state'])['state'] in ['open', 'paid']

    def write(self, cr, uid, ids, vals, context=None):
        if context is None:
            context = {}
        if not isinstance(ids, list):
            ids = [ids]

        res = super(AccountInvoice, self).write(cr, uid, ids, vals, context=context)

        if 'state' in vals and vals['state'] == 'open':
            sync_obj = self.pool.get('odoo.sync')
            sync_obj.common_sync_model_create_update(
                cr, uid, self._name, 'create', ids, context=context
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
            - tax = IVA
        """
        if context is None:
            context = {}
        tax_line_obj = self.pool.get('account.invoice.tax')
        account_obj = self.pool.get('account.account')
        sync_obj = self.pool.get('odoo.sync')

        tax_line_ids = tax_line_obj.search(
            cr, uid, [('invoice_id', '=', invoice_id)], context=context)
        res = []
        iese_tax_id = 0
        iese_amount = 0
        iva_tax_id = 0
        for tax_line in tax_line_obj.browse(cr, uid, tax_line_ids, context=context):
            if 'Impuesto especial' in tax_line.name:
                iese_tax_id = tax_line.tax_id.id
                iese_amount = tax_line.amount
            elif 'IVA' in tax_line.name:
                iva_tax_id = tax_line.tax_id.id

        odoo_iva_tax_id = sync_obj.get_odoo_id_by_erp_id(cr, uid, 'account.tax', iva_tax_id)
        iva_account_id = account_obj.search(cr, uid, [('code', 'like', '47560%0')])[0]
        odoo_iva_account_id = sync_obj.get_odoo_id_by_erp_id(
            cr, uid, 'account.account', iva_account_id)
        if iese_tax_id:
            res = [
                {
                    'name': u'Import IESE',
                    'quantity': 1,
                    'price_unit': iese_amount,
                    'tax_ids': [odoo_iva_tax_id],
                    'extra_operations_erp': 1,
                    'quantity_erp': 1,
                    'account_id': odoo_iva_account_id,
                }
            ]
        return res

    def hook_last_modifications(self, cr, uid, data, context=None):
        """
        Modify the data to sync with a constant:
        - payment_type = 375

        :param self: Description
        :param cr: Description
        :param uid: Description
        :param data: Description
        :param context: Description
        """
        if context is None:
            context = {}
        if data['move_type'] in ['in_refund', 'in_invoice']:
            data['preferred_payment_method_line_id'] = 375
        if data['ref'] is False:
            data['ref'] = ''
        return data


AccountInvoice()
