# -*- coding: utf-8 -*-
from osv import osv, fields
from som_sync_openerp.models.odoo_sync import STATIC_MODELS


class WizardSyncObjectOdoo(osv.osv_memory):
    _name = 'wizard.sync.object.odoo'
    _description = 'Wizard to sync object with Odoo'

    def action_sync(self, cursor, uid, ids, context=None):
        if context is None:
            context = {}
        from_model = context.get('from_model')
        active_ids = context.get('active_ids', [])

        if not from_model or not active_ids:
            return {'type': 'ir.actions.act_window_close'}

        sync_obj = self.pool.get('odoo.sync')
        wiz = self.browse(cursor, uid, ids[0], context=context)
        context['is_static'] = wiz.is_static

        if wiz.is_static:
            if not wiz.odoo_id:
                raise osv.except_osv(
                    "Error",
                    "You must specify an Odoo ID when syncing a static model."
                )
            if len(active_ids) > 1:
                raise osv.except_osv(
                    "Error",
                    "You can only sync one record at a time for static models."
                )
            context['odoo_id'] = wiz.odoo_id

        if from_model == 'odoo.sync':
            # Support execution from model odoo.sync
            for _id in active_ids:
                # Get the real model and res_id from odoo.sync record
                sync_data = sync_obj.browse(cursor, uid, _id)
                from_res_model = sync_data.model.model
                erp_id = sync_data.res_id
                if wiz.is_static:
                    sync_obj.syncronize_sync(
                        cursor, uid, from_res_model, 'sync', erp_id, context=context
                    )
                else:
                    sync_obj.common_sync_model_create_update(
                        cursor, uid, from_res_model, 'sync', erp_id, context=context
                    )
            return {'type': 'ir.actions.act_window_close'}

        # Normal execution from any model that can be synced
        for record_id in active_ids:
            if wiz.is_static:
                sync_obj.syncronize_sync(
                    cursor, uid, from_model, 'sync', record_id, context=context
                )
            else:
                sync_obj.common_sync_model_create_update(
                    cursor, uid, from_model, 'sync', record_id, context=context
                )

        return {'type': 'ir.actions.act_window_close'}

    def _get_default_value(self, cursor, uid, context=None):
        if context is None:
            context = {}
        from_model = context.get('from_model')
        is_static = from_model in STATIC_MODELS
        if not is_static and from_model == 'odoo.sync':
            # we check if model of odoo.sync is static
            active_ids = context.get('active_ids', [])
            sync_obj = self.pool.get('odoo.sync')
            sync_data = sync_obj.browse(cursor, uid, active_ids[0])
            from_res_model = sync_data.model.model
            is_static = from_res_model in STATIC_MODELS
        return is_static

    _columns = {
        "state": fields.selection([("init", "Init"), ("end", "End")], "State"),
        "info": fields.text("Description"),
        "is_static": fields.boolean("Is Static Model"),
        "odoo_id": fields.integer("Odoo ID"),
    }

    _defaults = {
        "state": lambda *a: "init",
        "is_static": _get_default_value,
    }


WizardSyncObjectOdoo()
