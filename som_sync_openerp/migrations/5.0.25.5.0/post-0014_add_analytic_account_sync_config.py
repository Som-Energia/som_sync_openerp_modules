# -*- coding: utf-8 -*-
from oopgrade.oopgrade import load_data_records


def up(cursor, installed_version):
    if not installed_version:
        return

    # Load only the new noupdate record, preserving unrelated configuration.
    load_data_records(
        cursor, 'som_sync_openerp', 'data/som_sync_openerp_data.xml',
        ['odoo_sync_model_config_account_analytic_account'], mode='init')


def down(cursor, installed_version):
    pass


migrate = up
