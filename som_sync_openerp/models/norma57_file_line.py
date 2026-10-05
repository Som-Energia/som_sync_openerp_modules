# -*- coding: utf-8 -*-
import logging

from osv import osv
from service.security import Sudo


logger = logging.getLogger('openerp.odoo.sync')


class Norma57FileLine(osv.osv):
    _name = 'norma57.file.line'
    _inherit = 'norma57.file.line'

    MAPPING_FIELDS_TO_SYNC = {
        'id': 'pnt_erp_id',
    }
    MAPPING_FK = {}
    MAPPING_CONSTANTS = {
        'pnt_source_model': 'norma57.file.line',
    }

    def write(self, cr, uid, ids, vals, context=None):
        if context is None:
            context = {}
        if not isinstance(ids, list):
            ids = [ids]

        confirmed_ids = []
        if vals.get('state') == 'confirmed':
            lines = self.read(cr, uid, ids, ['state'], context=context)
            confirmed_ids = [
                line['id'] for line in lines if line['state'] != 'confirmed'
            ]

        result = super(Norma57FileLine, self).write(
            cr, uid, ids, vals, context=context)

        if confirmed_ids:
            with Sudo(uid=1, gid=0):
                self.pool.get('odoo.sync').common_sync_model_create_update(
                    cr, uid, self._name, 'write', confirmed_ids, context=context)

        return result

    def _get_destination_journal_odoo_id(self, cr, uid, context=None):
        if context is None:
            context = {}
        value = self.pool.get('res.config').get(
            cr, uid, 'odoo_norma57_destination_journal', 0)
        try:
            journal_id = int(value)
        except (TypeError, ValueError):
            logger.warning('Invalid odoo_norma57_destination_journal: %s', value)
            journal_id = 0
        if not journal_id:
            raise Exception('odoo_norma57_destination_journal is not configured')
        return journal_id

    def _get_invoice_erp_id(self, cr, uid, line, context=None):
        if not line.resource:
            return False
        model, model_id = line.resource.split(',')
        if model == 'account.invoice':
            return int(model_id)
        if model != 'giscedata.facturacio.factura':
            raise Exception('Unsupported Norma57 resource: {}'.format(line.resource))
        invoice_id = self.pool.get('giscedata.facturacio.factura').read(
            cr, uid, int(model_id), ['invoice_id'], context=context).get('invoice_id')
        return invoice_id and invoice_id[0]

    def get_related_values(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        line = self.browse(cr, uid, id, context=context)
        invoice_id = self._get_invoice_erp_id(cr, uid, line, context=context)
        if not invoice_id:
            raise Exception('Norma57 line has no invoice')
        invoice = self.pool.get('account.invoice').read(
            cr, uid, invoice_id, ['number'], context=context)
        if not invoice.get('number'):
            raise Exception('Norma57 invoice has no number')
        return {
            'journal_id': self._get_destination_journal_odoo_id(
                cr, uid, context=context),
            'date': line.file_id.header_presentation_date,
            'amount': abs(line.amount),
            'payment_ref': '[FACTURA] {}'.format(invoice['number']),
        }

    def check_special_restrictions(self, cr, uid, id, context=None):
        return self.browse(cr, uid, id, context=context).state == 'confirmed'


Norma57FileLine()
