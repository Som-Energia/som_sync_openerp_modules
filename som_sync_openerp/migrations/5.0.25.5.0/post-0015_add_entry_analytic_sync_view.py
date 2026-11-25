# -*- coding: utf-8 -*-
from __future__ import absolute_import

from oopgrade.oopgrade import load_data
from tools import config
from tools.translate import trans_load


def up(cursor, installed_version):
    if not installed_version:
        return
    load_data(cursor, 'som_sync_openerp', 'views/reassign_move_analytics_view.xml',
              idref=None, mode='update')
    trans_load(cursor, '{}/som_sync_openerp/i18n/ca_ES.po'.format(config['addons_path']), 'ca_ES')


def down(cursor, installed_version):
    pass


migrate = up
