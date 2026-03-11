# -*- coding: utf-8 -*-
from __future__ import absolute_import
from destral import testing


class TestResMunicipi(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.rm_obj = self.openerp.pool.get("res.municipi")
        self.imd_obj = self.openerp.pool.get("ir.model.data")
        super(TestResMunicipi, self).setUp()

    def test_get_endpoint_suffix(self):
        country_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "base_extended", "ine_99999"
        )[1]

        suffix = self.rm_obj.get_endpoint_suffix(self.cursor, self.uid, country_id)

        self.assertEqual(suffix, '99999')
