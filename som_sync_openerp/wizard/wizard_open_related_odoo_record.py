# -*- coding: utf-8 -*-
from osv import osv


class WizardOpenRelatedOdooRecord(osv.osv_memory):
    _name = 'wizard.open.related.odoo.record'
    _description = 'Open related Odoo record in browser wizard'

    def open_odoo_record(self, cr, uid, ids, context=None):
        if context is None:
            context = {}

        model = context.get('from_model')
        active_ids = context.get('active_ids', [])

        if not active_ids:
            return {'type': 'ir.actions.act_window_close'}

        sync = self.pool.get(model).browse(
            cr, uid, active_ids[0], context=context
        )

        if not sync.odoo_url_record:
            raise osv.except_osv(
                'Error',
                'The selected sync record does not have an Odoo URL available.'
            )

        return {
            'type': 'ir.actions.act_url',
            'url': sync.odoo_url_record,
            'target': 'new',
        }


WizardOpenRelatedOdooRecord()
