# -*- coding: utf-8 -*-
import pooler

from oopgrade.oopgrade import load_data
from tools import config


def up(cursor, installed_version):
    if not installed_version:
        return
    if not config.updating_all:
        pooler.get_pool(cursor.dbname).get('odoo.sync')._auto_init(
            cursor, context={'module': 'som_sync_openerp'})

    # Group 5 accounts retain the original route; other account mappings
    # are shared between profiles. Orphan mappings cannot be classified.
    cursor.execute("""
        UPDATE odoo_sync AS sync SET sync_profile = 'shared'
        FROM account_account AS account, ir_model AS model
        WHERE sync.model = model.id AND model.model = 'account.account'
          AND sync.res_id = account.id
          AND COALESCE(account.code, '') NOT LIKE '5%'
          AND sync.sync_profile = 'all_in'
    """)
    cursor.execute("""
        ALTER TABLE odoo_sync DROP CONSTRAINT IF EXISTS odoo_sync_model_res_id_uniq
    """)
    cursor.execute("""
        ALTER TABLE odoo_sync ADD CONSTRAINT odoo_sync_model_res_id_uniq
        UNIQUE (model, res_id, sync_profile)
    """)
    if not config.updating_all:
        for path in ('data/som_sync_openerp_data.xml', 'views/odoo_sync_view.xml'):
            load_data(cursor, 'som_sync_openerp', path, idref=None, mode='update')


def down(cursor, installed_version):
    # Returning to one mapping per ERP record requires an explicit data decision.
    pass


migrate = up
