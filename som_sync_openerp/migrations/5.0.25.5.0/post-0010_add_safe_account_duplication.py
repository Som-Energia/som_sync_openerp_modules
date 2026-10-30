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
    pool = pooler.get_pool(cursor.dbname)

    for model in ('wizard.duplicate.account', 'wizard.duplicate.account.line'):
        logger.info('Registering account duplication model and fields: %s', model)
        pool.get(model)._auto_init(
            cursor, context={'module': 'som_sync_openerp'}
        )

    for path in (
            'wizard/wizard_duplicate_account_view.xml',
            'security/ir.model.access.csv'):
        logger.info('Loading safe account duplication data: %s', path)
        load_data(
            cursor, 'som_sync_openerp', path, idref=None, mode='update'
        )
    logger.info('Safe account duplication wizard and permissions loaded')


def down(cursor, installed_version):
    pass


migrate = up
