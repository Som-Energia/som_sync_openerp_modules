#  -*- coding: utf-8 -*-
from osv import osv
from service.security import Sudo


class PaymentOrder(osv.osv):
    _name = 'payment.order'
    _inherit = 'payment.order'

    MAPPING_FIELDS_TO_SYNC = {
        'id': 'pnt_erp_id',
        'name': 'name',
        'date_created': 'date',  # TODO: check if date_created is the one's
        'date_planned': 'sdd_required_collection_date',
    }
    MAPPING_FK = {
    }

    MAPPING_CONSTANTS = {
    }

    def get_related_values(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        payment_order = self.browse(cr, uid, id, context=context)
        lines = []
        sync_obj = self.pool.get('odoo.sync')
        for line in payment_order.line_ids:
            payment_line_vals = sync_obj.get_model_vals_to_sync(
                cr, uid, 'payment.line', line.id, context=context)
            lines.append(payment_line_vals)
        journal_erp_id = payment_order.mode.journal.id if payment_order.mode.journal else False
        journal_odoo_id = sync_obj.get_odoo_id_by_erp_id(cr, uid, 'account.journal', journal_erp_id)
        factor = -1 if payment_order.type == 'receivable' else 1
        res = {
            'batch_type': 'outbound' if payment_order.type == 'payable' else 'inbound',
            'journal_destiny': journal_odoo_id,
            'lines': lines,
            'amount': payment_order.total * factor,
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
