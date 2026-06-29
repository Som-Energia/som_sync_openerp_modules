# -*- coding: utf-8 -*-
import logging
import pooler

from tools import config


def up(cursor, installed_version):
    if not installed_version:
        return
    if config.updating_all:
        return

    logger = logging.getLogger('openerp.migration')
    logger.info("Creating pooler")
    pool = pooler.get_pool(cursor.dbname)

    logger.info("Creating new state manual pending in odoo.sync")
    pool.get('odoo.sync')._auto_init(
        cursor, context={'module': 'som_sync_openerp'}
    )
    logger.info("State created successfully")


def down(cursor, installed_version):
    pass


migrate = up
