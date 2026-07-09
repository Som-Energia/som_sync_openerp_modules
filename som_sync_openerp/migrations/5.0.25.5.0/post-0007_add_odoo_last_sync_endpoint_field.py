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

    logger.info('Creating new odoo_last_sync_endpoint field in odoo.sync')
    pool.get('odoo.sync')._auto_init(
        cursor, context={'module': 'som_sync_openerp'}
    )
    logger.info('Field created successfully')

    logger.info('Loading view XML with new odoo_last_sync_endpoint field')
    xmls = [
        'views/odoo_sync_view.xml',
    ]
    for xml_path in xmls:
        load_data(
            cursor,
            'som_sync_openerp',
            xml_path,
            idref=None,
            mode='update'
        )
    logger.info('odoo_sync_view.xml loaded successfully')


def down(cursor, installed_version):
    pass


migrate = up
