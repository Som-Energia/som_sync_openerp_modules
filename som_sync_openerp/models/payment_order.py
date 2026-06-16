#  -*- coding: utf-8 -*-
import requests

from oorq.decorators import job
from osv import osv
from service.security import Sudo
import logging


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
        is_splitted = self._is_order_splitted_invoices(cr, uid, payment_order)

        if is_splitted:
            return 'payment_orders/payments'

        mapping = {
            # (is_grouped, is_refund): 'model_name'
            (True, True): 'payment_order_batches_refunds',  # TODO: does not exists this endpoint!!
            (True, False): 'payment_orders/batches',
            (False, True): 'payment_order_refunds',
            (False, False): 'payment_orders',
        }
        return mapping.get((is_grouped, is_refund))

    def get_sync_state_on_creation(self, cr, uid, id, context=None):
        endpoint = self.get_mapping_model_post(cr, uid, id, context=context)
        if endpoint == 'payment_orders':
            return 'pending'
        return 'synced'

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
            (True, True): 'payment_method_line_id',  # payment_order_batches_refunds
            (True, False): 'payment_method_line_id',  # payment_orders/batches
            (False, True): 'method_id',  # payment_order_refunds
            (False, False): 'payment_method_line_id',  # payment_orders
        }
        return mapping.get((is_grouped, is_refund))

    def _get_journal_odoo_id(self, cr, uid, payment_order, context=None):
        if context is None:
            context = {}
        logger = logging.getLogger('openerp.odoo.sync')
        sync_obj = self.pool.get('odoo.sync')
        journal_obj = self.pool.get('account.journal')

        if not payment_order.mode or not payment_order.mode.bank_id:
            logger.warning(
                'Payment order %s has no payment mode bank configured',
                payment_order.id,
            )
            return False

        journal_ids = journal_obj.search(
            cr, uid, [('som_sync_bank_id', '=', payment_order.mode.bank_id.id)],
            context=context)
        if not journal_ids:
            logger.warning(
                'No account.journal found for bank account %s in payment order %s',
                payment_order.mode.bank_id.id, payment_order.id,
            )
            return False
        if len(journal_ids) > 1:
            logger.warning(
                'Multiple journal records found for bank account %s in payment order %s: %s',
                payment_order.mode.bank_id.id, payment_order.id, journal_ids,
            )
            return False

        journal_odoo_id = sync_obj.get_odoo_id_by_erp_id(
            cr, uid, 'account.journal', journal_ids[0])
        if not journal_odoo_id:
            logger.warning(
                'No Odoo mapping found for account.journal %s in payment order %s',
                journal_ids[0], payment_order.id,
            )
            return False
        return journal_odoo_id
    # ----------------------------------

    def _is_order_grouped_invoices(self, cr, uid, payment_order):
        logger = logging.getLogger('openerp.odoo.sync')
        logger.info('Checking if payment order %s has grouped invoices', payment_order.id)
        # We consider that a payment order has grouped invoices when at least one of its lines
        # is not directly linked to an invoice but has some invoice in its move lines.
        # We assume that if there are grouped invoices, they are all grouped and there are no
        # mixed cases with grouped and non-grouped invoices in the same payment order.
        for line in payment_order.line_ids:
            without_ml_inv_ref = not line.ml_inv_ref
            has_invoices = any([aml.invoice for aml in line.move_line_id.move_id.line_id])
            if without_ml_inv_ref and has_invoices:
                return True
            else:
                return False

    def _is_order_splitted_invoices(self, cr, uid, payment_order):
        logger = logging.getLogger('openerp.odoo.sync')
        logger.info('Checking if payment order %s has splitted invoices', payment_order.id)
        # We consider that a payment order has splitted invoices when at least one of its lines
        # is not directly linked to an invoice and has no invoices in its move lines.
        # We assume that if there are splitted invoices, they are all splitted and there are no
        # mixed cases with splitted and non-splitted invoices in the same payment order.
        for line in payment_order.line_ids:
            without_ml_inv_ref = not line.ml_inv_ref
            has_invoices = any([aml.invoice for aml in line.move_line_id.move_id.line_id])
            if without_ml_inv_ref and not has_invoices:
                return True
            else:
                return False

    def _is_order_refund(self, cr, uid, payment_order):
        logger = logging.getLogger('openerp.odoo.sync')
        logger.info('Checking if payment order %s is refund', payment_order.id)
        # TODO: cover case when grouped invoices with mixed types (refund and non refund)??
        # We consider that if the first line of the payment order is linked to a refund invoice,
        # then the payment order is a refund.
        # We assume that there are no mixed payment orders with refund and non-refund invoices.
        for line in payment_order.line_ids:
            if line.ml_inv_ref \
                    and line.ml_inv_ref.type == 'out_invoice' and line.ml_inv_ref.amount_total < 0:
                return True
            else:
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

    def _get_order_payment_lines_from_splitted_invoices(self, cr, uid, payment_order, context=None):
        """
        Gets the payment_ids and total amount for a payment.order with fraccionaments.
        Returns:
            payment_ids: list of Odoo account.payment ids
            amount: total amount of all fraccionaments
        """
        if context is None:
            context = {}

        sync_obj = self.pool.get('odoo.sync')
        aiff_obj = self.pool.get('account.invoice.fraccionament.fraccionaments')

        payment_ids = []
        amount_total = 0.0

        # we get fraccionament lines linked to the payment order through remesa_desti_id
        fraccl_ids = aiff_obj.search(
            cr, uid, [('remesa_desti_id', '=', payment_order.id)], context=context)

        # now we get all different fraccionaments linked to those lines
        fracc_read_ids = aiff_obj.read(
            cr, uid, fraccl_ids, ['invoice_fraccionament_id'], context=context)
        fracc_ids = list(set([
            f['invoice_fraccionament_id'][0]for f in fracc_read_ids if f['invoice_fraccionament_id']
        ]))

        # ensure all fraccionaments are synced so all fraccionaments lines exist in Odoo
        for fracc_id in fracc_ids:
            context_copy = context.copy()
            context_copy['from_fk_sync'] = True
            odoo_id, _ = sync_obj.common_sync_model_create_update(
                cr, uid, 'account.invoice.fraccionament',
                'sync', fracc_id, context_copy)

        # now we can get the odoo_ids of the fraccionaments lines
        for fraccl_id in fraccl_ids:
            payment_odoo_id = sync_obj.get_odoo_id_by_erp_id_from_odoo(
                cr, uid, 'account.invoice.fraccionament.fraccionaments', fraccl_id)
            if payment_odoo_id:
                payment_ids.append(payment_odoo_id)
                fraccl_data = aiff_obj.read(cr, uid, fraccl_id, ['import'], context=context)
                amount_total += fraccl_data['import']
            else:
                # if we don't find the odoo_id for a fraccionament line it means that the sync of
                # the parent fraccionament has failed. This way we force error in the payment order
                # sync and avoid having unsynced fraccionament lines linked to synced payment orders
                payment_ids.append(False)

        return payment_ids, round(amount_total, 2)

    def _build_splitted_related_values(self, cr, uid, payment_order, name, context=None):
        logger = logging.getLogger('openerp.odoo.sync')
        logger.info(
            'Building related values for payment order {} with splitted invoices'.format(
                payment_order.id))
        if context is None:
            context = {}
        conf_obj = self.pool.get('res.config')

        journal_odoo_id = self._get_journal_odoo_id(
            cr, uid, payment_order, context=context)
        metode_pagament_id = eval(
            conf_obj.get(cr, uid, 'odoo_customer_fraccionaments_payment_method', 0))

        payment_ids, amount = self._get_order_payment_lines_from_splitted_invoices(
            cr, uid, payment_order, context=context)

        return {
            'destination_journal_id': journal_odoo_id,
            'payment_method_line_id': metode_pagament_id,
            'payment_ids': payment_ids,
            'amount': amount,
            'name': name,
        }

    def _build_normal_related_values(
            self, cr, uid, payment_order, name, is_grouped, is_refund, context=None):

        logger = logging.getLogger('openerp.odoo.sync')
        logger.info(
            'Building related values for payment order {}'.format(
                payment_order.id))
        if context is None:
            context = {}
        conf_obj = self.pool.get('res.config')

        journal_odoo_id = self._get_journal_odoo_id(
            cr, uid, payment_order, context=context)
        lines = []
        pl_inv_ids = []

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
        logger.info(
            'Processing lines with discrepancies for payment order {}: lines: {}'.format(
                payment_order.id, len(lines)))
        inv_obj.process_lines_with_discrepancies(
            cr, uid, pl_inv_ids, lines, is_grouped=is_grouped, context=context)

        po_total_amount = round(sum([line['amount'] for line in lines]), 2)

        if payment_order.type == 'payable':
            metode_pagament_id = eval(conf_obj.get(cr, uid, 'odoo_provider_payment_method', 0))
            # all amounts to negative when payment_order_batch payable
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

        return {
            journal_odoo_field_name: journal_odoo_id,
            payment_method_odoo_field_name: metode_pagament_id,
            'lines': lines,
            'amount': po_total_amount,
            'name': name,
            'batch_type': 'outbound' if payment_order.type == 'payable' else 'inbound',
        }

    def get_related_values(self, cr, uid, id, context=None):
        if context is None:
            context = {}

        payment_order = self.browse(cr, uid, id, context=context)
        name = payment_order.name or ''

        is_refund = self._is_order_refund(cr, uid, payment_order)
        is_grouped = self._is_order_grouped_invoices(cr, uid, payment_order)
        is_splitted = self._is_order_splitted_invoices(cr, uid, payment_order)

        logger = logging.getLogger('openerp.odoo.sync')
        logger.info(
            'Payment order {} - is_refund: {}, is_grouped: {}, is_splitted: {}'.format(
                payment_order.id, is_refund, is_grouped, is_splitted))

        if is_refund:
            name = 'RECT_{}'.format(payment_order.name)

        if is_splitted:
            return self._build_splitted_related_values(
                cr, uid, payment_order, name, context=context)

        return self._build_normal_related_values(
            cr, uid, payment_order, name, is_grouped, is_refund, context=context)

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
            https://*****/api/v1/payment_orders/13228/status  # noqa:E501

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

        url_base = "{}payment_orders/{}/status".format(
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
