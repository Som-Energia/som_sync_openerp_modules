#  -*- coding: utf-8 -*-
from osv import osv

import logging


logger = logging.getLogger('openerp.odoo.sync')


class Norma57File(osv.osv):
    _name = 'norma57.file'
    _inherit = 'norma57.file'

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

    def _get_bank_statement_line_values(self, cr, uid, line, context=None):
        if context is None:
            context = {}

        invoice_erp_id = self._get_line_invoice_erp_id(cr, uid, line, context=context)
        if not invoice_erp_id:
            raise Exception('Norma57 line has no invoice')
        inv_obj = self.pool.get('account.invoice')
        invoice = inv_obj.read(
            cr, uid, invoice_erp_id, ['number'], context=context)
        if not invoice.get('number'):
            raise Exception('Norma57 invoice has no number')
        return {
            'pnt_source_model': 'norma57.file.line',
            'pnt_erp_id': line.id,
            'journal_id': self._get_destination_journal_odoo_id(
                cr, uid, context=context),
            'date': line.file_id.header_presentation_date,
            'amount': abs(line.amount),
            'payment_ref': '[FACTURA] {}'.format(invoice['number']),
        }

    def sync_bank_statement_lines(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        norma57_file = self.browse(cr, uid, id, context=context)
        sync_obj = self.pool.get('odoo.sync')
        result = True
        for line in norma57_file.lines:
            if line.state != 'confirmed':
                continue
            if not sync_obj.sync_bank_statement_line(
                    cr, uid, 'norma57.file.line', line.id,
                    self._get_bank_statement_line_values(
                        cr, uid, line, context=context), context=context):
                result = False
        return result

    def confirm(self, cursor, uid, ids, context=None):
        if context is None:
            context = {}

        payment_context = context.copy()
        payment_context['skip_bank_statement_line_payment_sync'] = True
        res = super(Norma57File, self).confirm(
            cursor, uid, ids, context=payment_context)

        if not isinstance(ids, (list, tuple)):
            ids = [ids]

        for norma57_id in ids:
            self.sync_bank_statement_lines(
                cursor, uid, norma57_id, context=context)

        return res


Norma57File()
