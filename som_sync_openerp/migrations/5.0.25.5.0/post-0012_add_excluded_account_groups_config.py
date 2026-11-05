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
    pooler.get_pool(cursor.dbname)

    logger.info('Loading excluded account groups configuration')
    load_data(
        cursor,
        'som_sync_openerp',
        'data/som_sync_openerp_data.xml',
        idref=None,
        mode='update'
    )
    logger.info('Excluded account groups configuration loaded successfully')


def down(cursor, installed_version):
    pass


migrate = up
