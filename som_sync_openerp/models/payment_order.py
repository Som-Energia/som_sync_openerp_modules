#  -*- coding: utf-8 -*-
from osv import osv
from service.security import Sudo
import json


class PaymentOrder(osv.osv):
    _name = 'payment.order'
    _inherit = 'payment.order'

    MAPPING_FIELDS_TO_SYNC = {
        'id': 'pnt_erp_id',
        'date_created': 'date',  # TODO: check if date_created is the one's
        'date_planned': 'sdd_required_collection_date',
    }
    MAPPING_FK = {
    }

    MAPPING_CONSTANTS = {
    }

    def get_mapping_model_post(self, cr, uid, id, context=None):
        payment_order = self.browse(cr, uid, id, context=context)
        is_grouped = self._is_order_grouped_invoices(cr, uid, payment_order)
        is_refund = self._is_order_refund(cr, uid, payment_order)

        mapping = {
            # (is_grouped, is_refund): 'model_name'
            (True, True): 'payment_order_batches_refunds',
            (True, False): 'payment_order_batches',
            (False, True): 'payment_order_refunds',
            (False, False): 'payment_orders',
        }
        return mapping.get((is_grouped, is_refund))

    def get_endpoint_odoo_record_suffix(self, cr, uid, id, odoo_id, context=None):
        """
        This method is used to get the suffix to identify the record in Odoo
        - for customer: :/odoo/action-375/57
        - for provider': /odoo/action-376/55
        """
        # TODO: action_name as a setting
        type_endpoint_mapping = {
            'receivable': 'action-375',
            'payable': 'action-376',
        }
        if context is None:
            context = {}
        payment_order = self.browse(cr, uid, id, context=context)
        if payment_order.type in type_endpoint_mapping:
            return '/{}/{}'.format(type_endpoint_mapping[payment_order.type], odoo_id)
        else:
            return False

    def _get_journal_odoo_field_name(self, cr, uid, is_grouped, is_refund, context=None):
        mapping = {
            # (is_grouped, is_refund): 'model_name'
            (True, True): 'journal_id',  # payment_order_batches_refunds
            (True, False): 'destination_journal_id',  # payment_order_batches
            (False, True): 'journal_id',  # payment_order_refunds
            (False, False): 'journal_destiny',  # payment_orders
        }
        return mapping.get((is_grouped, is_refund))

    def _get_total_amount_difference(self, inv_read_sync_record):
        """
        This method is used to get the total amount difference between Odoo and ERP
        inv_read_sync_record format expected:
        {
            'id': 1,
            'res_id': 20,
            'odoo_id': 57,
            'odoo_last_update_result': '{...}'
        }
        """
        if not inv_read_sync_record or 'odoo_last_update_result' not in inv_read_sync_record:
            return 0
        odoo_last_update_result = inv_read_sync_record['odoo_last_update_result']
        if not odoo_last_update_result:
            return 0
        if not isinstance(odoo_last_update_result, dict):
            try:
                odoo_last_update_result = json.loads(odoo_last_update_result)
            except Exception:
                return 0
        if 'data' in odoo_last_update_result and 'metadata' in odoo_last_update_result['data'] \
                and isinstance(odoo_last_update_result['data']['metadata'], list) \
                and len(odoo_last_update_result['data']['metadata']) > 0 \
                and 'pnt_amount_total_erp_difference' in odoo_last_update_result['data']['metadata'][0]:  # noqa: E501
            discrepancy = (
                odoo_last_update_result['data']['metadata'][0]['pnt_amount_total_erp_difference'])
            if discrepancy:
                return discrepancy
        return 0

    def _is_order_grouped_invoices(self, cr, uid, payment_order):
        for line in payment_order.line_ids:
            if not line.ml_inv_ref:
                return True
        return False

    def _is_order_refund(self, cr, uid, payment_order):
        # TODO: cover case when grouped invoices with mixed types (refund and non refund)??
        for line in payment_order.line_ids:
            if line.ml_inv_ref \
                    and line.ml_inv_ref.type == 'out_invoice' and line.ml_inv_ref.amount_total < 0:
                return True
        return False

    def _get_order_lines_from_invoices(self, cr, uid, payment_line, context=None):
        """
         This method is used to get the values of the payment line to sync with Odoo
         we expect to have the following format in Odoo:
         {
            'invoice_id': 125753,
            'amount': 182.12
         }
        """
        sync_obj = self.pool.get('odoo.sync')
        if context is None:
            context = {}

        payment_line_vals = sync_obj.get_model_vals_to_sync(
            cr, uid, 'payment.line', payment_line.id, context=context)
        payment_line_vals['amount'] = abs(payment_line_vals['amount'])
        return payment_line_vals, [payment_line.ml_inv_ref.id] if payment_line.ml_inv_ref else None

    def _get_order_line_from_grouped_invoices(self, cr, uid, payment_line, context=None):
        """
         This method is used to get the values of the payment line to sync with Odoo
         we expect to have the following format in Odoo:
        {
            'invoice_ids': [125753, 125754],
            'amount': 182.12
        }
        """
        sync_obj = self.pool.get('odoo.sync')
        if context is None:
            context = {}
        payment_line_vals = {'amount': abs(payment_line.amount)}
        odoo_invoice_ids = []
        erp_invoice_ids = []
        for am in payment_line.move_line_id.move_id.line_id:
            if not am.invoice:
                continue
            erp_invoice_id = am.invoice.id
            # we get the odoo id of the invoice in order to link it to the payment line
            context_copy = context.copy()
            context_copy['from_fk_sync'] = True
            odoo_id, _ = sync_obj.common_sync_model_create_update(
                cr, uid, 'account.invoice', 'sync', erp_invoice_id, context_copy)
            odoo_invoice_ids.append(odoo_id)
            erp_invoice_ids.append(erp_invoice_id)
        payment_line_vals['invoice_ids'] = odoo_invoice_ids
        return payment_line_vals, erp_invoice_ids

    def _process_payment_lines_with_discrepancies(
            self, cr, uid, pl_inv_ids, lines, is_grouped=False, context=None):
        """
        This method is used to process the payment lines to get the values to sync with Odoo,
        and update the amount to sync in order to avoid discrepancies in Odoo
        """
        if context is None:
            context = {}
        sync_obj = self.pool.get('odoo.sync')
        # we read sync records for invoices linked to payment lines with warning
        inv_sync_with_diff_ids = sync_obj.search(cr, uid, [
            ('model.model', '=', 'account.invoice'),
            ('res_id', 'in', pl_inv_ids),
            ('sync_state', '=', 'synced_with_warning'),
            ('odoo_last_update_result', '!=', False),
        ])
        amount_difference_total = 0
        if not inv_sync_with_diff_ids:
            return lines
        # we read the sync records with specific fields to avoid performance issues
        inv_read_sync_records = sync_obj.read(
            cr, uid, inv_sync_with_diff_ids, ['res_id', 'odoo_id', 'odoo_last_update_result'])
        for inv_read_sync_record in inv_read_sync_records:
            # we get the amount difference from the last synchronization
            amount_difference = self._get_total_amount_difference(inv_read_sync_record)
            # we update the amount to sync of specific lines with discrepancy
            odoo_inv_id = inv_read_sync_record['odoo_id']
            found = False
            for line in lines:
                if is_grouped:
                    found = line.get('invoice_ids', False) and odoo_inv_id in line['invoice_ids']
                else:
                    found = line.get('invoice_id', False) and line['invoice_id'] == odoo_inv_id
                if found:
                    line['amount'] = round(line['amount'] + amount_difference, 2)
                    amount_difference_total += amount_difference
                    break

        return amount_difference_total

    def get_related_values(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        sync_obj = self.pool.get('odoo.sync')
        conf_obj = self.pool.get('res.config')

        payment_order = self.browse(cr, uid, id, context=context)
        name = payment_order.name or ''
        journal_erp_id = payment_order.mode.journal.id if payment_order.mode.journal else False
        journal_odoo_id = sync_obj.get_odoo_id_by_erp_id(cr, uid, 'account.journal', journal_erp_id)

        lines = []
        pl_inv_ids = []

        is_refund = self._is_order_refund(cr, uid, payment_order)
        is_grouped = self._is_order_grouped_invoices(cr, uid, payment_order)

        if is_refund:
            # Factures FE negatives, les tractem diferent a Odoo
            name = 'RECT_{}'.format(payment_order.name)

        if is_grouped:
            function_to_get_lines = self._get_order_line_from_grouped_invoices
        else:
            function_to_get_lines = self._get_order_lines_from_invoices

        for line in payment_order.line_ids:
            payment_line_vals, erp_invoice_ids = function_to_get_lines(
                cr, uid, line, context=context)
            lines.append(payment_line_vals)
            if erp_invoice_ids:
                pl_inv_ids.extend(erp_invoice_ids)

        # at this point we're sure that invoices are synced, and we have to treat the discrepancies
        # if there are any, in order to update the amounts to sync with Odoo and avoid sync issues
        amount_difference_total = (
            self._process_payment_lines_with_discrepancies(
                cr, uid, pl_inv_ids, lines, is_grouped, context=context)
        )

        if payment_order.type == 'payable':
            metode_pagament_id = eval(conf_obj.get(cr, uid, 'odoo_provider_payment_method', 0))
        else:
            metode_pagament_id = eval(conf_obj.get(cr, uid, 'odoo_customer_payment_method', 0))

        journal_odoo_field_name = self._get_journal_odoo_field_name(
            cr, uid, is_grouped, is_refund, context=context)
        res = {
            'batch_type': 'outbound' if payment_order.type == 'payable' else 'inbound',
            journal_odoo_field_name: journal_odoo_id,
            'lines': lines,
            'amount': round((abs(payment_order.total) + amount_difference_total), 2),
            'name': name,
            'method_id': metode_pagament_id,
        }
        return res

    def check_special_restrictions(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        order = self.browse(cr, uid, id)
        if order.state != 'done' or not order.mode.som_sync_odoo:
            return False
        return True

    def write(self, cr, uid, ids, vals, context=None):
        if context is None:
            context = {}
        if not isinstance(ids, list):
            ids = [ids]

        res = super(PaymentOrder, self).write(cr, uid, ids, vals, context=context)

        if 'state' in vals and vals['state'] == 'done':
            with Sudo(uid=1, gid=0):
                sync_obj = self.pool.get('odoo.sync')
                sync_obj.common_sync_model_create_update(
                    cr, uid, self._name, 'create', ids, context=context
                )

        return res


PaymentOrder()
