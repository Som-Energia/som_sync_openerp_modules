#  -*- coding: utf-8 -*-
from osv import osv
from service.security import Sudo
import json


class AccountInvoice(osv.osv):
    _name = 'account.invoice'
    _inherit = 'account.invoice'

    MAPPING_FIELDS_TO_SYNC = {
        "id": "pnt_erp_id",
        "number": "number",
        "partner_id": "partner_id",
        "journal_id": "journal_id",
        "date_invoice": "invoice_date",
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

    def _get_total_amount_difference(self, inv_read_sync_record):
        """
        Get the total amount difference between ERP and Odoo for a synced invoice with warning,
        checking the metadata stored in odoo_last_update_result field in odoo.sync record.

        Return a tuple with the amount difference and the move_type of the invoice
        to apply the correct factor in case of refunds.

        inv_read_sync_record:
            record read from odoo.sync with fields ['res_id', 'odoo_id', 'odoo_last_update_result']
        return:
            (amount_difference, move_type)
        """
        if not inv_read_sync_record or 'odoo_last_update_result' not in inv_read_sync_record:
            return 0, None
        odoo_last_update_result = inv_read_sync_record['odoo_last_update_result']
        if not odoo_last_update_result:
            return 0, None
        if not isinstance(odoo_last_update_result, dict):
            try:
                odoo_last_update_result = json.loads(odoo_last_update_result)
            except Exception:
                return 0, None
        if 'data' in odoo_last_update_result and 'metadata' in odoo_last_update_result['data'] \
                and isinstance(odoo_last_update_result['data']['metadata'], list) \
                and len(odoo_last_update_result['data']['metadata']) > 0 \
                and 'pnt_amount_total_erp_difference' in odoo_last_update_result['data']['metadata'][0]:  # noqa: E501
            discrepancy = (
                odoo_last_update_result['data']['metadata'][0]['pnt_amount_total_erp_difference'])
            if discrepancy:
                return discrepancy, odoo_last_update_result['data']['metadata'][0]['move_type']
        return 0, None

    def process_lines_with_discrepancies(
            self, cr, uid, invoice_ids, lines, is_grouped=False, context=None):
        """
        Update amounts in lines using discrepancy information stored in odoo.sync
        for invoice sync records with warning.

        Expected line format:
        - non-grouped: {'invoice_id': <odoo_invoice_id>, 'amount': <float>}
        - grouped: {'invoice_ids': [<odoo_invoice_id>, ...], 'amount': <float>}
        """
        if context is None:
            context = {}
        sync_obj = self.pool.get('odoo.sync')

        inv_sync_with_diff_ids = sync_obj.search(cr, uid, [
            ('model.model', '=', 'account.invoice'),
            ('res_id', 'in', invoice_ids),
            ('sync_state', '=', 'synced_with_warning'),
            ('odoo_last_update_result', '!=', False),
        ])
        if not inv_sync_with_diff_ids:
            return True

        inv_read_sync_records = sync_obj.read(
            cr, uid, inv_sync_with_diff_ids, ['res_id', 'odoo_id', 'odoo_last_update_result'])
        for inv_read_sync_record in inv_read_sync_records:
            amount_difference, move_type = self._get_total_amount_difference(inv_read_sync_record)
            if amount_difference == 0:
                continue

            factor = -1 if move_type and 'out_refund' in move_type else 1
            odoo_inv_id = inv_read_sync_record['odoo_id']
            for line in lines:
                if is_grouped:
                    found = line.get('invoice_ids', False) and odoo_inv_id in line['invoice_ids']
                    if found:
                        line['amount'] = round(
                            line['amount'] * factor + amount_difference, 2) * factor
                        break
                else:
                    found = line.get('invoice_id', False) and line['invoice_id'] == odoo_inv_id
                    if found:
                        line['amount'] = round(line['amount'] + amount_difference, 2)
                        break
        return True

    def get_endpoint_odoo_record_suffix(self, cr, uid, id, odoo_id, context=None):
        """
        This method is used to get the suffix to identify the record in Odoo
        - for customer invoices: : /odoo/customer-invoices/160440
        - for customer invoices with type 'out_refund': /odoo/credit-notes/160440
        - for provider invoices: /odoo/vendor-bills/160440
        - for provider invoices with type 'in_refund': no way /odoo/action-247/160440
        """
        type_endpoint_mapping = {
            'out_invoice': 'customer-invoices',
            'out_refund': 'credit-notes',
            'in_invoice': 'vendor-bills',
        }
        if context is None:
            context = {}
        account_invoice = self.browse(cr, uid, id, context=context)
        if account_invoice.type in type_endpoint_mapping:
            return '/{}/{}'.format(type_endpoint_mapping[account_invoice.type], odoo_id)
        else:
            return False

    def _process_invoice_lines(self, cr, uid, account_invoice, factor_reverse=1, context=None):
        """
        This method is used to process the invoice lines to get the values to sync with Odoo,
        and agrupate them by account and taxes.
        """
        original_res = {}
        energy_tax_id = False
        for line in account_invoice.invoice_line:
            sync_obj = self.pool.get('odoo.sync')
            tax_obj = self.pool.get('account.tax')
            account_obj = self.pool.get('account.account')
            ail_vals = sync_obj.get_model_vals_to_sync(
                cr, uid, 'account.invoice.line', line.id, context=context)
            account_id = ail_vals['account_id']
            erp_account_id = sync_obj.get_erp_id_by_odoo_id(cr, uid, 'account.account', account_id)
            account_code = account_obj.read(cr, uid, erp_account_id, ['code'])['code']

            # Check if it's an energy line to get the tax
            if not energy_tax_id and line.product_id and line.product_id.categ_id and \
                    line.product_id.categ_id.name.lower() == 'energia':
                for tax_line in line.invoice_line_tax_id:
                    if 'IVA' in tax_line.name or 'IGIC' in tax_line.name:
                        energy_tax_id = tax_line.id
                        break

            # Remove IESE taxes
            new_tax_ids = []
            for tax in line.invoice_line_tax_id:
                if 'Impuesto especial' not in tax_obj.read(cr, uid, tax.id, ['name'])['name']:
                    odoo_tax_id = sync_obj.get_odoo_id_by_erp_id(cr, uid, 'account.tax', tax.id)
                    new_tax_ids.append(odoo_tax_id)

            ail_vals['tax_ids'] = new_tax_ids
            dict_key = "{}_{}".format(ail_vals['account_id'], ail_vals['tax_ids'])

            # Agrupate lines by account_id and taxes
            if original_res.get(dict_key, False) and \
                    original_res[dict_key]['tax_ids'] == ail_vals['tax_ids']:
                original_res[dict_key]['price_unit'] = original_res[dict_key]['price_unit'] + \
                    ail_vals['price_subtotal']
            else:
                original_res[dict_key] = {
                    'account_id': account_id,
                    'quantity': 1 * factor_reverse,
                    'name': "Agrupació {}".format(account_code),
                    'price_unit': ail_vals['price_subtotal'],
                    'extra_operations_erp': 1,
                    'quantity_erp': 1,
                    'tax_ids': ail_vals['tax_ids'],
                }
        return original_res, energy_tax_id

    def get_related_values(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        account_invoice = self.browse(cr, uid, id, context=context)
        original_res = {}
        res = []
        energy_tax_id = False
        invoice_type = account_invoice.type
        factor_reverse = -1 if account_invoice.amount_total < 0 else 1

        amount_total = factor_reverse * account_invoice.amount_total
        # Process invoice lines to get the values to sync with Odoo
        original_res, energy_tax_id = self._process_invoice_lines(
            cr, uid, account_invoice, factor_reverse=factor_reverse, context=context)

        # Add tax lines needed for the sync with Odoo
        res.extend(
            self.add_taxes_lines_needed_for_sync(
                cr, uid, id, energy_tax_id, factor_reverse=factor_reverse, context=context)
        )

        # Get corrected base untaxed and tax amount, only with IVA, IGIC and Retenciones amounts
        amount_tax = 0.0
        for tax_line in account_invoice.tax_line:
            if 'IVA' in tax_line.tax_id.name or 'IGIC' in tax_line.name \
                    or 'Retenciones' in tax_line.name:
                amount_tax = amount_tax + tax_line.amount

        # Save agrupated lines
        for k, v in original_res.items():
            v['price_unit'] = round(v['price_unit'], 2)
            if v.get('tax_ids', False) == []:
                v.pop('tax_ids')
            res.append(v)

        # type invoice treatment whem total amount_total < 0
        if factor_reverse < 0:
            if invoice_type == 'out_invoice':
                invoice_type = 'out_refund'
            elif invoice_type == 'in_invoice':
                invoice_type = 'in_refund'
            elif invoice_type == 'out_refund':
                invoice_type = 'out_invoice'
            elif invoice_type == 'in_refund':
                invoice_type = 'in_invoice'

        dict_res = {
            'date': account_invoice.date_invoice,
            'move_type': invoice_type,
            'invoice_line_ids': res,
            'amount_untaxed': factor_reverse * (account_invoice.amount_total - amount_tax),
            'amount_tax': factor_reverse * amount_tax,
            'amount_total': amount_total,
        }

        # 'ref' field for refund invoices
        if account_invoice.rectifying_id and account_invoice.rectifying_id.number:
            ref = account_invoice.rectifying_id.number
            dict_res['ref'] = ref
        if account_invoice.type == 'in_invoice':
            dict_res['ref'] = account_invoice.origin or ''

        return dict_res

    def check_special_restrictions(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        return self._journal_is_syncrozable(cr, uid, id, context=context) and \
            self._is_invoice_syncrozable(cr, uid, id, context=context)

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
        inv_states = {}
        if 'state' in vals and vals['state'] == 'open':
            for _id in ids:
                inv_states[_id] = self.read(cr, uid, _id, ['state'], context=context)['state']

        res = super(AccountInvoice, self).write(cr, uid, ids, vals, context=context)

        sync_obj = self.pool.get('odoo.sync')
        if 'state' in vals and vals['state'] == 'open':
            for _id in ids:
                if inv_states[_id] in ['draft']:
                    with Sudo(uid=1, gid=0):
                        sync_obj.common_sync_model_create_update(
                            cr, uid, self._name, 'create', _id, context=context
                        )

        return res

    def add_taxes_lines_needed_for_sync(
            self, cr, uid, invoice_id, energy_tax_id, factor_reverse=1, context=None):
        """
        This method is called from account.invoice to add the tax lines
        needed for the sync with Odoo.
        Lines to add if we have IESE tax lines:
        * Extra line 1:
            - quantity = 1
            - price_unit = amount of the tax IESE line
            - tax = IVA from energy lines
        """
        if context is None:
            context = {}
        tax_line_obj = self.pool.get('account.invoice.tax')
        account_obj = self.pool.get('account.account')
        sync_obj = self.pool.get('odoo.sync')

        tax_line_ids = tax_line_obj.search(
            cr, uid, [('invoice_id', '=', invoice_id)], context=context)
        res = []
        iese_amount = 0
        iva_tax_id = energy_tax_id or 0
        for tax_line in tax_line_obj.browse(cr, uid, tax_line_ids, context=context):
            if 'Impuesto especial' in tax_line.name:
                iese_amount = tax_line.amount
                break

        odoo_iva_tax_id = sync_obj.get_odoo_id_by_erp_id(cr, uid, 'account.tax', iva_tax_id)
        iva_account_id = account_obj.search(cr, uid, [('code', 'like', '47560%0')])[0]
        odoo_iva_account_id = sync_obj.get_odoo_id_by_erp_id(
            cr, uid, 'account.account', iva_account_id)
        if iese_amount:
            res = [
                {
                    'name': u'Import IESE',
                    'quantity': factor_reverse * 1,
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
        Modify the payment method for providers invoices with a config
          variable odoo_provider_payment_method

        :param self: Description
        :param cr: Description
        :param uid: Description
        :param data: Description
        :param context: Description
        """
        config_obj = self.pool.get('res.config')
        odoo_payment_method_id = config_obj.get(cr, uid, 'odoo_provider_payment_method', 375)
        if context is None:
            context = {}
        if data['move_type'] in ['in_refund', 'in_invoice']:
            data['preferred_payment_method_line_id'] = odoo_payment_method_id
        return data

    def _get_amount_tolerance(self, cr, uid):
        """
        Returns the configured tolerance for invoice amount discrepancies.
        Reads 'odoo_sync_invoice_amount_tolerance' from res.config.
        Defaults to 0.02 if not set or if the config model is not available.
        """
        DEFAULT_TOLERANCE = 0.02
        config_obj = self.pool.get('res.config')
        val = eval(config_obj.get(cr, uid, 'odoo_sync_invoice_amount_tolerance', DEFAULT_TOLERANCE))
        return float(val)

    def hook_after_odoo_creation(self, cr, uid, response, sync_vals):
        """
        After create Invoice in Odoo, we check if we have amounts discrepancies
        checking metadata in data response:
        response['data']['metadata'][0]:
        - "pnt_amount_total_erp_difference" = float
        If pnt_amount_total_erp_difference <= tolerance -> synced_with_warning
        If pnt_amount_total_erp_difference > tolerance  -> error
        Tolerance is configured via 'odoo_sync_invoice_amount_tolerance' (default 0.02).
        """
        if not response:
            return
        # response to dict if it's not already a dict
        if not isinstance(response, dict):
            response = json.loads(response)
        if response and 'data' in response and 'metadata' in response['data']:
            metadata = response['data']['metadata'][0]
            difference = abs(metadata.get('pnt_amount_total_erp_difference', 0.0))
            if difference > 0:
                tolerance = self._get_amount_tolerance(cr, uid)
                if difference <= tolerance:
                    sync_vals['sync_state'] = 'synced_with_warning'
                else:
                    sync_vals['sync_state'] = 'error'


AccountInvoice()
