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
    pooler.get_pool(cursor.dbname)

    logger.info('Updating XML data for account code normalization config')
    xmls = [
        'data/som_sync_openerp_data.xml',
    ]
    for xml_path in xmls:
        load_data(
            cursor,
            'som_sync_openerp',
            xml_path,
            idref=None,
            mode='update'
        )
    logger.info('Account code normalization config XML data updated successfully')


def down(cursor, installed_version):
    pass


migrate = up
