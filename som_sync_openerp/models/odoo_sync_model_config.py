#  -*- coding: utf-8 -*-
from osv import osv, fields


class OdooSyncModelConfig(osv.osv):
    _name = 'odoo.sync.model.config'
    _description = 'Odoo sync models configuration'
    _rec_name = 'model_id'

    _columns = {
        'model_id': fields.many2one('ir.model', 'Model', required=True),
        'auto_sync': fields.boolean(
            'Auto sync',
            help='If checked, sync is triggered automatically on create/write/unlink.'),
        'async_enabled': fields.boolean(
            'Async enabled',
            help='If checked, sync is done asynchronously.'),
    }

    _sql_constraints = [
        ('model_id_uniq', 'unique (model_id)', ('Model must be unique.')),
    ]

    _defaults = {
        'auto_sync': lambda *a, **k: False,
        'async_enabled': lambda *a, **k: True,
    }


OdooSyncModelConfig()
