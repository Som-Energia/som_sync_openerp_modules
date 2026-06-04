#  -*- coding: utf-8 -*-
from osv import osv


class AccountInvoiceFraccionament(osv.osv):
    _name = 'account.invoice.fraccionament'
    _inherit = 'account.invoice.fraccionament'

    # Fields mapped directly to Odoo payload fields
    # erp field -> odoo field
    MAPPING_FIELDS_TO_SYNC = {
    }
    MAPPING_FK = {}
    MAPPING_CONSTANTS = {}

    def get_mapping_model_post(self, cr, uid, erp_id, context=None):
        """
        Returns the POST endpoint suffix for fraccionaments.
        Maps to: POST /api/v1/invoices/payments
        """
        return 'invoices/payments'

    def get_endpoint_odoo_record_suffix(self, cr, uid, id, odoo_id, context=None):
        """
        Fraccionament lines are synced as payments linked to an invoice in Odoo.
        There is no direct URL for a payment in Odoo, so we return the URL of
        the related invoice instead:
        /customer-invoices/<odoo_invoice_id>
        """
        if context is None:
            context = {}
        fraccionament = self.read(cr, uid, id, ['invoice_id'], context=context)
        invoice_erp_id = fraccionament['invoice_id'][0] if fraccionament['invoice_id'] else None
        if not invoice_erp_id:
            return False
        sync_obj = self.pool.get('odoo.sync')
        invoice_odoo_id = sync_obj.get_odoo_id_by_erp_id(
            cr, uid, 'account.invoice', invoice_erp_id)
        if not invoice_odoo_id:
            return False
        return '/customer-invoices/{}'.format(invoice_odoo_id)

    def get_related_values(self, cr, uid, id, context=None):
        """
        Builds the full payload for the Odoo fraccionament endpoint:
        {
            'erp_id': <erp id of the fraccionament>,
            'invoice_id': <odoo_id of the invoice>,
            'payment_method_line_id': <odoo_id of the payment method line>,
            'amount_total': <total amount>,
            'lines': [
                {
                    'pnt_erp_id': <erp id of the fraccionament line>,
                    'amount': <amount>,
                    'payment_date': <due date>,
                },
                ...
            ]
        }
        """
        if context is None:
            context = {}

        sync_obj = self.pool.get('odoo.sync')
        conf_obj = self.pool.get('res.config')

        fraccionament = self.browse(cr, uid, id, context=context)

        context_copy = context.copy()
        context_copy['from_fk_sync'] = True

        # Sync the invoice and get its Odoo ID
        invoice_erp_id = fraccionament.invoice_id.id
        invoice_odoo_id, _ = sync_obj.common_sync_model_create_update(
            cr, uid, 'account.invoice', 'sync', fraccionament.invoice_id.id, context_copy)

        payment_method_odoo_id = eval(
            conf_obj.get(cr, uid, 'odoo_customer_fraccionaments_payment_method', 0))

        # Build the lines from fraccionament_ids (account.invoice.fraccionament.fraccionaments)
        frac_line_obj = self.pool.get('account.invoice.fraccionament.fraccionaments')
        frac_line_ids = frac_line_obj.search(
            cr, uid, [('invoice_fraccionament_id', '=', id)], context=context)
        frac_lines_data = frac_line_obj.read(
            cr, uid, frac_line_ids, ['import', 'data_venciment'], context=context)

        lines = []
        for frac_line in frac_lines_data:
            lines.append({
                'pnt_erp_id': frac_line['id'],
                'amount': frac_line['import'],
                'payment_date': str(frac_line['data_venciment']),
            })

        res = {
            'erp_id': invoice_erp_id,
            'invoice_id': invoice_odoo_id,
            'payment_method_line_id': payment_method_odoo_id,
            'amount_total': fraccionament.import_a_fraccionar,
            'lines': lines,
        }
        return res


AccountInvoiceFraccionament()
