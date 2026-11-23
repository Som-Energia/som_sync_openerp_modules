# -*- coding: utf-8 -*-
import os
import runpy
import sys
import types
import unittest
from xml.etree import ElementTree


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODULE = os.path.join(ROOT, 'som_sync_openerp')
RECORD_ID = 'odoo_sync_model_config_account_analytic_account'


class AnalyticAccountConfigMigrationTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        package = types.ModuleType('oopgrade')
        module = types.ModuleType('oopgrade.oopgrade')
        module.load_data_records = lambda *args, **kwargs: self.calls.append(
            (args, kwargs))
        saved_modules = dict(sys.modules)
        try:
            sys.modules['oopgrade'] = package
            sys.modules['oopgrade.oopgrade'] = module
            self.migration = runpy.run_path(os.path.join(
                MODULE, 'migrations', '5.0.25.5.0',
                'post-0014_add_analytic_account_sync_config.py'))
        finally:
            for name in ('oopgrade', 'oopgrade.oopgrade'):
                if name in saved_modules:
                    sys.modules[name] = saved_modules[name]
                else:
                    sys.modules.pop(name, None)

    def test_upgrade_loads_only_analytic_config_in_init_mode(self):
        cursor = object()

        self.migration['migrate'](cursor, '0.1')

        self.assertEqual(self.calls, [(
            (cursor, 'som_sync_openerp', 'data/som_sync_openerp_data.xml',
             [RECORD_ID]),
            {'mode': 'init'},
        )])
        data = ElementTree.parse(os.path.join(
            MODULE, 'data', 'som_sync_openerp_data.xml'))
        records = data.findall(".//record[@id='{}']".format(RECORD_ID))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].get('model'), 'odoo.sync.model.config')
        fields = dict((field.get('name'), field) for field in records[0])
        self.assertEqual(
            fields['model_id'].get('search'),
            "[('model', '=', 'account.analytic.account')]")
        self.assertEqual(fields['auto_sync'].text, 'False')
        self.assertEqual(fields['async_enabled'].text, 'False')

    def test_fresh_install_does_not_run_migration(self):
        self.migration['migrate'](object(), None)

        self.assertEqual(self.calls, [])

    def test_down_does_not_remove_existing_config(self):
        self.migration['down'](object(), '0.1')

        self.assertEqual(self.calls, [])
