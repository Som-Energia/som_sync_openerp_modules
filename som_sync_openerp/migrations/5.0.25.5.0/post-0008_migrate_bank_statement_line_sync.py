# -*- coding: utf-8 -*-
from oopgrade.oopgrade import load_data
from tools import config


def up(cursor, installed_version):
    if not installed_version or config.updating_all:
        return

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
            AND name IN (
                'action_wizard_sync_odoo_from_norma57_file',
                'get_synced_records_odoo_action_norma57_file'
            )
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

    load_data(
        cursor, 'som_sync_openerp', 'data/som_sync_openerp_data.xml',
        idref=None, mode='update')
    load_data(
        cursor, 'som_sync_openerp', 'views/odoo_sync_view.xml',
        idref=None, mode='update')
    load_data(
        cursor, 'som_sync_openerp', 'wizard/wizard_sync_object_odoo_view.xml',
        idref=None, mode='update')


def down(cursor, installed_version):
    pass


migrate = up
