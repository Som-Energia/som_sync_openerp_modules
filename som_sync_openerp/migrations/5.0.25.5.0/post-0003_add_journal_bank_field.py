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
    logger.info("Creating pooler")
    pool = pooler.get_pool(cursor.dbname)

    logger.info("Creating new field som_sync_bank_id on model account.journal")
    pool.get('account.journal')._auto_init(
        cursor, context={'module': 'som_sync_openerp'}
    )
    logger.info("Field created successfully")

    logger.info("Updating XML views/account_journal_view.xml")
    load_data(
        cursor,
        'som_sync_openerp',
        'views/account_journal_view.xml',
        idref=None,
        mode='update'
    )
    logger.info("XMLs succesfully updated.")


def down(cursor, installed_version):
    pass


migrate = up
