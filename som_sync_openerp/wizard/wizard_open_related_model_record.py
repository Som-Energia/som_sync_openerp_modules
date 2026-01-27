# -*- coding: utf-8 -*-
from osv import osv


class WizardOpenRelatedModelRecord(osv.osv_memory):
    _name = 'wizard.open.related.record'
    _description = 'Open related model record wizard'

    def open_record(self, cr, uid, ids, context=None):
        if context is None:
            context = {}

        model = context.get('from_model')
        active_ids = context.get('active_ids', [])

        if not active_ids:
            return {'type': 'ir.actions.act_window_close'}

        sync = self.pool.get(model).browse(
            cr, uid, active_ids[0], context=context
        )

        if not sync.model or not sync.res_id:
            raise osv.except_osv(
                'Error',
                'The selected sync record does not have a related model or record ID.'
            )

        return {
            'type': 'ir.actions.act_window',
            'name': 'Related Model Record',
            'res_model': sync.model.model,
            'res_id': sync.res_id,
            'view_type': 'form',
            'view_mode': 'form',
            'target': 'current',
        }


WizardOpenRelatedModelRecord()
