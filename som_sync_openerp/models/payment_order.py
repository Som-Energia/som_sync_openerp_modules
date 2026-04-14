#  -*- coding: utf-8 -*-
import requests

from oorq.decorators import job
from osv import osv
from service.security import Sudo


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

    # TODO: ask Punt to unify field names in API
    # ----------------------------------
    def _get_journal_odoo_field_name(self, cr, uid, is_grouped, is_refund, context=None):
        mapping = {
            # (is_grouped, is_refund): 'model_name'
            (True, True): 'journal_id',  # payment_order_batches_refunds
            (True, False): 'destination_journal_id',  # payment_order_batches
            (False, True): 'journal_id',  # payment_order_refunds
            (False, False): 'destination_journal_id',  # payment_orders
        }
        return mapping.get((is_grouped, is_refund))

    def _get_payment_method_odoo_field_name(self, cr, uid, is_grouped, is_refund, context=None):
        mapping = {
            # (is_grouped, is_refund): 'model_name'
            (True, True): 'payment_method_id',  # payment_order_batches_refunds
            (True, False): 'payment_method_id',  # payment_order_batches
            (False, True): 'method_id',  # payment_order_refunds
            (False, False): 'payment_method_id',  # payment_orders
        }
        return mapping.get((is_grouped, is_refund))
    # ----------------------------------

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
        odoo_invoice_ids = []
        erp_invoice_ids = []
        amount_total = 0
        for aml in payment_line.move_line_id.move_id.line_id:
            if not aml.invoice:
                continue
            erp_invoice_id = aml.invoice.id
            # we get the odoo id of the invoice in order to link it to the payment line
            context_copy = context.copy()
            context_copy['from_fk_sync'] = True
            odoo_id, _ = sync_obj.common_sync_model_create_update(
                cr, uid, 'account.invoice', 'sync', erp_invoice_id, context_copy)
            odoo_invoice_ids.append(odoo_id)
            erp_invoice_ids.append(erp_invoice_id)
            amount_total += round((aml.credit - aml.debit), 2)
        payment_line_vals = {'amount': round(amount_total, 2)}
        payment_line_vals['invoice_ids'] = odoo_invoice_ids
        return payment_line_vals, erp_invoice_ids

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
        inv_obj = self.pool.get('account.invoice')
        inv_obj.process_lines_with_discrepancies(
            cr, uid, pl_inv_ids, lines, is_grouped=is_grouped, context=context
        )

        # we calculte the total amount of lines
        po_total_amount = round(sum([line['amount'] for line in lines]), 2)

        if payment_order.type == 'payable':
            metode_pagament_id = eval(conf_obj.get(cr, uid, 'odoo_provider_payment_method', 0))
            # all amounts to negative when payment_oder_batch payable
            if is_grouped:
                po_total_amount = -abs(po_total_amount)
                for line in lines:
                    line['amount'] = -abs(line['amount'])
        else:
            metode_pagament_id = eval(conf_obj.get(cr, uid, 'odoo_customer_payment_method', 0))

        journal_odoo_field_name = self._get_journal_odoo_field_name(
            cr, uid, is_grouped, is_refund, context=context)

        payment_method_odoo_field_name = self._get_payment_method_odoo_field_name(
            cr, uid, is_grouped, is_refund, context=context)

        res = {
            journal_odoo_field_name: journal_odoo_id,
            payment_method_odoo_field_name: metode_pagament_id,
            'lines': lines,
            'amount': po_total_amount,
            'name': name,
            'batch_type': 'outbound' if payment_order.type == 'payable' else 'inbound',
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

    @job(queue='sync_odoo', timeout=3600)
    def update_pending_state(self, cursor, uid,
                             openerp_id, context=None):
        if context is None:
            context = {}
        self.update_pending_state_sync(cursor, uid, openerp_id, context=context)

    def update_pending_state_sync(self, cr, uid, erp_id, context=None):
        """
            Request:
            https://som-energia_odoo_75_puntsistemes.pulls.puntsistemes.cloud/api/v1/payment_orders/status/13228  # noqa:E501

            Response:
            {
                "success": true,
                "message": "Record found successfully",
                "data": {
                    "odoo_id": 92,
                    "erp_id": 13228,
                    "status": "processing",
                    "processed": false,
                    "confirmed": false
                }
            }
        """
        if context is None:
            context = {}

        sync_obj = self.pool.get('odoo.sync')
        odoo_url_api, odoo_api_key = sync_obj._get_conn_params(cr, uid)
        sync_vals = {}

        url_base = "{}payment_orders/status/{}".format(
            odoo_url_api, erp_id
        )
        headers = {
            "X-API-Key": odoo_api_key,
            "Accept": "application/json",
        }
        response = requests.get(url_base, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if data and 'success' in data and data.get('success', False) and \
                    data.get('data', False) and data['data'].get('status', False):
                if data['data']['status'] == 'done':
                    sync_vals.update({'sync_state': 'synced', 'update_last_sync': True})
                elif data['data']['status'] == 'error':
                    sync_vals.update({
                        'sync_state': 'error',
                        'update_last_sync': True,
                        'odoo_last_update_result': response
                    })

            if sync_vals:
                odoo_id = data['data']['odoo_id'] if data['data'].get('odoo_id', False) else False
                final_context = context.copy()
                final_context.update(sync_vals)
                sync_obj.update_odoo_id(cr, uid, self._name, erp_id, odoo_id, context=final_context)
                return True
        return False


PaymentOrder()
