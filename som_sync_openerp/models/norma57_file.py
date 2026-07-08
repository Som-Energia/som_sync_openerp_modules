#  -*- coding: utf-8 -*-
from oorq.decorators import job
from osv import osv
from service.security import Sudo

from .odoo_exceptions import ForeingKeyNotAvailable

import logging


logger = logging.getLogger('openerp.odoo.sync')


class Norma57File(osv.osv):
    _name = 'norma57.file'
    _inherit = 'norma57.file'

    MAPPING_FIELDS_TO_SYNC = {
        'id': 'pnt_erp_id',
        'header_presentation_date': 'date',
    }
    MAPPING_FK = {}
    MAPPING_CONSTANTS = {
        'batch_type': 'inbound',
    }

    def get_mapping_model_post(self, cr, uid, id, context=None):
        return 'payment_orders'

    def get_sync_state_on_creation(self, cr, uid, id, context=None):
        return 'pending'

    def get_endpoint_odoo_record_suffix(self, cr, uid, id, odoo_id, context=None):
        return '/action-375/{}'.format(odoo_id)

    def _get_config_odoo_id(self, cr, uid, key, context=None):
        if context is None:
            context = {}
        conf_obj = self.pool.get('res.config')
        value = conf_obj.get(cr, uid, key, 0)
        try:
            return int(value)
        except (TypeError, ValueError):
            logger.warning('Invalid %s config value: %s', key, value)
            return 0

    def _get_destination_journal_odoo_id(self, cr, uid, context=None):
        journal_odoo_id = self._get_config_odoo_id(
            cr, uid, 'odoo_norma57_destination_journal', context=context)
        if not journal_odoo_id:
            raise Exception('odoo_norma57_destination_journal is not configured')
        return journal_odoo_id

    def _get_payment_method_line_odoo_id(self, cr, uid, context=None):
        payment_method_line_id = self._get_config_odoo_id(
            cr, uid, 'odoo_norma57_payment_method', context=context)
        if not payment_method_line_id:
            raise Exception('odoo_norma57_payment_method is not configured')
        return payment_method_line_id

    def _get_line_invoice_erp_id(self, cr, uid, line, context=None):
        if context is None:
            context = {}
        if not line.resource:
            return False

        model, model_id = line.resource.split(',')
        if model == 'account.invoice':
            return int(model_id)

        if model != 'giscedata.facturacio.factura':
            logger.warning('Unsupported Norma57 resource: %s', line.resource)
            raise Exception('Unsupported Norma57 resource: {}'.format(line.resource))

        model_id = int(model_id)
        factura_obj = self.pool.get('giscedata.facturacio.factura')
        invoice_id = factura_obj.read(
            cr, uid, model_id, ['invoice_id'], context=context).get('invoice_id')
        if not invoice_id:
            return False
        return invoice_id[0]

    def _build_line_values(self, cr, uid, line, context=None):
        if context is None:
            context = {}

        sync_obj = self.pool.get('odoo.sync')
        invoice_erp_id = self._get_line_invoice_erp_id(cr, uid, line, context=context)
        if not invoice_erp_id:
            raise ForeingKeyNotAvailable('account.invoice,False')

        context_copy = context.copy()
        context_copy['from_fk_sync'] = True
        invoice_odoo_id, _ = sync_obj.common_sync_model_create_update(
            cr, uid, 'account.invoice', 'sync', invoice_erp_id, context_copy)
        if not invoice_odoo_id:
            raise ForeingKeyNotAvailable('account.invoice,{}'.format(invoice_erp_id))

        return {
            'invoice_id': invoice_odoo_id,
            'amount': abs(line.amount),
        }, invoice_erp_id

    def get_related_values(self, cr, uid, id, context=None):
        if context is None:
            context = {}

        norma57_file = self.browse(cr, uid, id, context=context)
        inv_obj = self.pool.get('account.invoice')
        destination_journal_id = self._get_destination_journal_odoo_id(
            cr, uid, context=context)
        payment_method_line_id = self._get_payment_method_line_odoo_id(
            cr, uid, context=context)
        lines = []
        invoice_ids = []

        for line in norma57_file.lines:
            if line.state != 'confirmed':
                continue
            line_vals, invoice_id = self._build_line_values(cr, uid, line, context=context)
            lines.append(line_vals)
            invoice_ids.append(invoice_id)

        if not lines:
            raise Exception('Norma57 file has no syncable confirmed invoice lines')

        inv_obj.process_lines_with_discrepancies(
            cr, uid, invoice_ids, lines, is_grouped=False, context=context)

        total_amount = round(sum([line['amount'] for line in lines]), 2)

        return {
            'destination_journal_id': destination_journal_id,
            'payment_method_line_id': payment_method_line_id,
            'name': norma57_file.name or '',
            'sdd_required_collection_date': norma57_file.header_presentation_date,
            'amount': total_amount,
            'lines': lines,
        }

    def check_special_restrictions(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        norma57_file = self.browse(cr, uid, id, context=context)
        return any([line.state == 'confirmed' for line in norma57_file.lines])

    def confirm(self, cursor, uid, ids, context=None):
        if context is None:
            context = {}

        res = super(Norma57File, self).confirm(cursor, uid, ids, context=context)

        if not isinstance(ids, (list, tuple)):
            ids = [ids]

        with Sudo(uid=1, gid=0):
            sync_obj = self.pool.get('odoo.sync')
            for norma57_id in ids:
                sync_obj.common_sync_model_create_update(
                    cursor, uid, 'norma57.file', 'write', norma57_id, context=context)

        return res

    @job(queue='sync_odoo', timeout=3600)
    def update_pending_state(self, cursor, uid, openerp_id, context=None):
        if context is None:
            context = {}
        self.update_pending_state_sync(cursor, uid, openerp_id, context=context)

    def update_pending_state_sync(self, cr, uid, erp_id, context=None):
        if context is None:
            context = {}

        sync_obj = self.pool.get('odoo.sync')
        return sync_obj.poll_payment_order_status_sync(
            cr, uid, self._name, erp_id, context=context)


Norma57File()
