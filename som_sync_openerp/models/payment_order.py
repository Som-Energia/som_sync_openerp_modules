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

    def get_related_values(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        sync_obj = self.pool.get('odoo.sync')
        conf_obj = self.pool.get('res.config')

        payment_order = self.browse(cr, uid, id, context=context)
        name = payment_order.name or ''
        journal_erp_id = payment_order.mode.journal.id if payment_order.mode.journal else False
        journal_odoo_id = sync_obj.get_odoo_id_by_erp_id(cr, uid, 'account.journal', journal_erp_id)
        factor = -1 if payment_order.type == 'receivable' else 1

        lines = []
        pl_inv_ids = []
        if payment_order.line_ids:
            line = payment_order.line_ids[0]
            if line.ml_inv_ref.type == 'out_invoice' and line.ml_inv_ref.amount_total < 0:
                # Factures FE negatives, les tractem diferent a Odoo
                name = 'RECT_{}'.format(payment_order.name)
        for line in payment_order.line_ids:
            payment_line_vals = sync_obj.get_model_vals_to_sync(
                cr, uid, 'payment.line', line.id, context=context)
            payment_line_vals['amount'] = payment_line_vals['amount'] * factor
            if line.ml_inv_ref:
                pl_inv_ids.append(line.ml_inv_ref.id)
            lines.append(payment_line_vals)

        # at this point we're sure that invoices are synced
        # we read sync records for invoices linked to payment lines with warning
        # in order to get the amount difference between ERP and Odoo if exists
        # and update the amount to sync in order to avoid discrepancies in Odoo
        inv_sync_with_diff_ids = sync_obj.search(cr, uid, [
            ('model.model', '=', 'account.invoice'),
            ('res_id', 'in', pl_inv_ids),
            ('sync_state', '=', 'synced_with_warning'),
            ('odoo_last_update_result', '!=', False),
        ])
        if inv_sync_with_diff_ids:
            # we read the sync records with specific fields to avoid performance issues
            inv_read_sync_records = sync_obj.read(
                cr, uid, inv_sync_with_diff_ids, ['res_id', 'odoo_id', 'odoo_last_update_result'])
            for inv_read_sync_record in inv_read_sync_records:
                # we get the amount difference from the last synchronization
                amount_difference = self._get_total_amount_difference(inv_read_sync_record)
                # we update the amount to sync of specific lines with discrepancy
                odoo_inv_id = inv_read_sync_record['odoo_id']
                for line in lines:
                    if line['invoice_id'] == odoo_inv_id:
                        line['amount'] += amount_difference
                        break

        if payment_order.type == 'payable':
            metode_pagament_id = eval(conf_obj.get(cr, uid, 'odoo_provider_payment_method', 0))
        else:
            metode_pagament_id = eval(conf_obj.get(cr, uid, 'odoo_customer_payment_method', 0))

        res = {
            'batch_type': 'outbound' if payment_order.type == 'payable' else 'inbound',
            'journal_destiny': journal_odoo_id,
            'lines': lines,
            'amount': payment_order.total * factor,
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
