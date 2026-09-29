# -*- coding: utf-8 -*-
import logging
import pooler

from oopgrade.oopgrade import load_data
from tools import config


def up(cursor, installed_version):
    if not installed_version or config.updating_all:
        return

    logger = logging.getLogger('openerp.migration')
    logger.info('Creating bank statement line fields in odoo.sync')
    pool = pooler.get_pool(cursor.dbname)
    pool.get('odoo.sync')._auto_init(
        cursor, context={'module': 'som_sync_openerp'}
    )
    load_data(
        cursor,
        'som_sync_openerp',
        'views/odoo_sync_view.xml',
        idref=None,
        mode='update'
    )


def down(cursor, installed_version):
    pass


migrate = up
