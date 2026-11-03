# -*- coding: utf-8 -*-
import logging

from addons import get_module_resource
from tools import config
from tools.translate import trans_load


def up(cursor, installed_version):
    if not installed_version:
        return
    if config.updating_all:
        return

    logger = logging.getLogger('openerp.migration')
    logger.info('Loading Catalan translations for account duplication')
    filename = get_module_resource('som_sync_openerp', 'i18n', 'ca_ES.po')
    trans_load(cursor, filename, 'ca_ES')
    logger.info('Catalan account duplication translations loaded successfully')


def down(cursor, installed_version):
    pass


migrate = up
