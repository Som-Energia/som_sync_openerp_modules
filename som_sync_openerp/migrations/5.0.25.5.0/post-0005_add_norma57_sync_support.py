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

    logger.info('Initializing norma57.file sync extension')
    pool.get('norma57.file')._auto_init(
        cursor, context={'module': 'som_sync_openerp'}
    )
    logger.info('norma57.file sync extension initialized successfully')

    logger.info('Updating XML data for Norma57 sync support')
    xmls = [
        'data/som_sync_openerp_data.xml',
        'views/odoo_sync_view.xml',
        'wizard/wizard_sync_object_odoo_view.xml',
        'wizard/wizard_open_related_model_record_view.xml',
    ]
    for xml_path in xmls:
        load_data(
            cursor,
            'som_sync_openerp',
            xml_path,
            idref=None,
            mode='update'
        )
    logger.info('Norma57 sync XML data updated successfully')


def down(cursor, installed_version):
    pass


migrate = up
