# -*- coding: utf-8 -*-
import logging
import pooler

from oopgrade.oopgrade import load_data
from tools import config


def up(cursor, installed_version):
    if not installed_version:
        return
    if config.updating_all:
        return

    logger = logging.getLogger('openerp.migration')
    logger.info('Creating pooler')
    pool = pooler.get_pool(cursor.dbname)

    logger.info(
        'Creating Norma57 payment entry sync fields on model odoo.sync'
    )
    pool.get('odoo.sync')._auto_init(
        cursor, context={'module': 'som_sync_openerp'}
    )
    logger.info('Norma57 payment entry sync fields created successfully')

    logger.info('Loading XML data with Norma57 payment entry config')
    load_data(
        cursor,
        'som_sync_openerp',
        'data/som_sync_openerp_data.xml',
        idref=None,
        mode='update'
    )
    logger.info('Norma57 payment entry config loaded successfully')


def down(cursor, installed_version):
    pass


migrate = up
