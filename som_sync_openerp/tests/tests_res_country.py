# -*- coding: utf-8 -*-
from __future__ import absolute_import
import mock
from destral import testing
from ..models import odoo_sync


class TestResCountry(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.rc_obj = self.openerp.pool.get("res.country")
        self.imd_obj = self.openerp.pool.get("ir.model.data")
        super(TestResCountry, self).setUp()

    def test_get_endpoint_suffix(self):
        country_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "base", "es"
        )[1]

        suffix = self.rc_obj.get_endpoint_suffix(self.cursor, self.uid, country_id)

        self.assertEqual(suffix, 'ES')

    @mock.patch.object(odoo_sync.OdooSync, "sync_model_enabled_amplified")
    @mock.patch.object(odoo_sync.OdooSync, "syncronize_sync")
    def test__create_triggers_async(self, mock_syncronize_sync, mock_sync_model_enabled_amplified):
        # sync_model_enabled_amplified returns (sync_enabled, auto_sync, async_enabled)
        mock_sync_model_enabled_amplified.return_value = (True, True, True)

        self.rc_obj.create(self.cursor, self.uid, {
            'name': 'Test Country',
            'code': 'XX',
            'code_alpha3': 'XTX',
        })

        mock_syncronize_sync.assert_called_once()
