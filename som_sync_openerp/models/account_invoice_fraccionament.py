#  -*- coding: utf-8 -*-
from osv import osv


class AccountInvoiceFraccionament(osv.osv):
    _name = 'account.invoice.fraccionament'
    _inherit = 'account.invoice.fraccionament'

    # Fields mapped directly to Odoo payload fields
    # erp field -> odoo field
    MAPPING_FIELDS_TO_SYNC = {
        'id': 'erp_id',
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
        if context is None:
            context = {}
        return '/odoo/invoices/payments/{}'.format(odoo_id)

    def get_related_values(self, cr, uid, id, context=None):
        """
        Builds the full payload for the Odoo fraccionament endpoint:
        {
            'invoice_id': <odoo_id of the invoice>,
            'payment_method_id': <odoo_id of the payment method>,
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
        fraccionament = self.browse(cr, uid, id, context=context)

        context_copy = context.copy()
        context_copy['from_fk_sync'] = True

        # Sync the invoice and get its Odoo ID
        invoice_odoo_id, _ = sync_obj.common_sync_model_create_update(
            cr, uid, 'account.invoice', 'sync', fraccionament.invoice_id.id, context_copy)

        # TODO: from where can we get the payment method in ERP? For now, hardcoded
        payment_method_odoo_id = 411

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
            'invoice_id': invoice_odoo_id,
            'payment_method_id': payment_method_odoo_id,
            'amount_total': fraccionament.import_a_fraccionar,
            'lines': lines,
        }
        return res


AccountInvoiceFraccionament()
