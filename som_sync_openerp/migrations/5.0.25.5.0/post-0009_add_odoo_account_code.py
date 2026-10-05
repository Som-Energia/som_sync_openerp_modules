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

    logger.info('Creating odoo_account_code field on account.account')
    pool.get('account.account')._auto_init(
        cursor, context={'module': 'som_sync_openerp'}
    )
    logger.info('Field created successfully')

    logger.info('Loading account account views')
    load_data(
        cursor,
        'som_sync_openerp',
        'views/account_account_view.xml',
        idref=None,
        mode='update'
    )
    logger.info('Views loaded successfully')


def down(cursor, installed_version):
    pass


migrate = up
