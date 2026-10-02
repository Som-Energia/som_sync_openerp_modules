# -*- coding: utf-8 -*-
import pooler

from oopgrade.oopgrade import load_data
from tools import config


def up(cursor, installed_version):
    if not installed_version or config.updating_all:
        return

    for field_name in (
            'pnt_bank_statement_line_odoo_id',
            'pnt_bank_statement_line_last_result',
            'pnt_bank_statement_line_last_request',
            'pnt_bank_statement_line_last_endpoint'):
        cursor.execute('ALTER TABLE odoo_sync DROP COLUMN IF EXISTS %s' % field_name)

    cursor.execute("""
        DELETE FROM odoo_sync_model_config
        WHERE model_id IN (
            SELECT id FROM ir_model WHERE model = 'norma57.file'
        )
    """)
    cursor.execute("""
        DELETE FROM ir_values
        WHERE model = 'norma57.file'
        AND name = 'Synchronize with Odoo'
    """)
    cursor.execute("""
        DELETE FROM ir_act_window
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'som_sync_openerp'
            AND name = 'action_wizard_sync_odoo_from_norma57_file'
        )
    """)
    cursor.execute("""
        DELETE FROM ir_model_data
        WHERE module = 'som_sync_openerp'
        AND name IN (
            'odoo_sync_model_config_norma57_file',
            'action_wizard_sync_odoo_from_norma57_file',
            'value_wizard_sync_odoo_from_norma57_file',
            'get_synced_records_odoo_action_norma57_file'
        )
    """)

    pool = pooler.get_pool(cursor.dbname)
    pool.get('odoo.sync')._auto_init(
        cursor, context={'module': 'som_sync_openerp'}
    )
    load_data(
        cursor, 'som_sync_openerp', 'data/som_sync_openerp_data.xml',
        idref=None, mode='update')
    load_data(
        cursor, 'som_sync_openerp', 'views/odoo_sync_view.xml',
        idref=None, mode='update')


def down(cursor, installed_version):
    pass


migrate = up
