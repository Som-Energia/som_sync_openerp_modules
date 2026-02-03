# -*- coding: utf-8 -*-
from destral import testing
from mock import MagicMock


class TestResPartnerAddress(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.rpa_obj = self.openerp.pool.get("res.partner.address")
        self.imd_obj = self.openerp.pool.get("ir.model.data")
        self.sync_obj = self.openerp.pool.get("odoo.sync")
        super(TestResPartnerAddress, self).setUp()

    def test_get_endpoint_suffix(self):
        partner_address_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "base", "res_partner_address_8"
        )[1]
        partner_id = self.rpa_obj.browse(self.cursor, self.uid, partner_address_id).partner_id.id
        context = {
            'sync_state': 'synced',
        }
        odoo_partner_id = 4001
        self.sync_obj.update_odoo_id(
            self.cursor, self.uid, "res.partner", partner_id, odoo_partner_id, context)
        suffix = self.rpa_obj.get_endpoint_suffix(self.cursor, self.uid, partner_address_id)
        self.assertEqual(suffix, "contact/4001/invoice")

    def test__create_triggers_sync(self):
        # sync_model_enabled_amplified returns (sync_enabled, auto_sync, async_enabled)
        self.sync_obj.sync_model_enabled_amplified = MagicMock(
            return_value=(True, True, True))
        self.sync_obj.syncronize = MagicMock()

        # Perform create operation
        self.rpa_obj.create(
            self.cursor,
            self.uid,
            {
                'nv': 'New Street Name',
            },
        )

        self.sync_obj.syncronize.assert_called_once()

    def test__create__autosync_not_enabled_no_trigger(self):
        # sync_model_enabled_amplified returns (sync_enabled, auto_sync, async_enabled)
        self.sync_obj.sync_model_enabled_amplified = MagicMock(
            return_value=(True, False, False))
        self.sync_obj.syncronize = MagicMock()
        self.sync_obj.syncronize_sync = MagicMock()

        # Perform create operation on a field that does not trigger sync
        self.rpa_obj.create(
            self.cursor,
            self.uid,
            {'nv': 'New City Name'},
        )

        # Assert that the sync method was not called
        self.sync_obj.syncronize.assert_not_called()
        self.sync_obj.syncronize_sync.assert_not_called()

    def test__write_triggers_async(self):
        partner_address_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "base", "res_partner_address_8"
        )[1]
        # sync_model_enabled_amplified returns (sync_enabled, auto_sync, async_enabled)
        self.sync_obj.sync_model_enabled_amplified = MagicMock(
            return_value=(True, True, True))
        self.sync_obj.syncronize = MagicMock()

        # Perform write operation
        self.rpa_obj.write(
            self.cursor,
            self.uid,
            partner_address_id,
            {'nv': 'New Street Name'},
        )

        self.sync_obj.syncronize.assert_called_once()

    def test__write__autosync_not_enabled_no_trigger(self):
        partner_address_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "base", "res_partner_address_8"
        )[1]
        # sync_model_enabled_amplified returns (sync_enabled, auto_sync, async_enabled)
        self.sync_obj.sync_model_enabled_amplified = MagicMock(
            return_value=(True, False, False))
        self.sync_obj.syncronize = MagicMock()
        self.sync_obj.syncronize_sync = MagicMock()

        # Perform write operation on a field that does not trigger sync
        self.rpa_obj.write(
            self.cursor,
            self.uid,
            partner_address_id,
            {'nv': 'New City Name'},
        )

        # Assert that the sync method was not called
        self.sync_obj.syncronize.assert_not_called()
        self.sync_obj.syncronize_sync.assert_not_called()
