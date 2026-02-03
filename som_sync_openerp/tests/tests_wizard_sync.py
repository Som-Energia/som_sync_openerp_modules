# -*- coding: utf-8 -*-
from destral import testing
from mock import MagicMock, call, ANY


class TestWizardSyncObjectOdoo(testing.OOTestCaseWithCursor):
    def setUp(self):
        self.wizard_obj = self.openerp.pool.get('wizard.sync.object.odoo')
        self.sync_obj = self.openerp.pool.get('odoo.sync')
        self.imd_obj = self.openerp.pool.get("ir.model.data")
        super(TestWizardSyncObjectOdoo, self).setUp()

    def test_action_sync__res_partner(self):
        # Mock syncronize_sync method
        self.sync_obj.syncronize_sync = MagicMock()

        context = {
            'from_model': 'res.partner',
            'active_ids': [1, 2, 3]
        }
        wiz_id = self.wizard_obj.create(self.cursor, self.uid, {}, context=context)
        self.wizard_obj.action_sync(self.cursor, self.uid, [wiz_id], context=context)

        # Verify syncronize_sync was called for each id
        self.assertEqual(self.sync_obj.syncronize_sync.call_count, 3)

        # Verify arguments of the last call
        self.sync_obj.syncronize_sync.assert_called_with(
            self.cursor, self.uid, 'res.partner', 'sync', 3, context=context
        )

    def test_action_sync__odoo_sync(self):
        osdemo_1 = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "odoo_partner_already_syncred"
        )[1]
        osdemo_2 = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "odoo_country_pending"
        )[1]
        osdemo_3 = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "odoo_country_state_error"
        )[1]

        # Mock syncronize_sync method
        self.sync_obj.syncronize_sync = MagicMock()

        context = {
            'from_model': 'odoo.sync',
            'active_ids': [osdemo_1, osdemo_2, osdemo_3]
        }
        wiz_id = self.wizard_obj.create(self.cursor, self.uid, {}, context=context)
        self.wizard_obj.action_sync(self.cursor, self.uid, [wiz_id], context=context)

        # Verify syncronize_sync was called for each id
        self.assertEqual(self.sync_obj.syncronize_sync.call_count, 3)

        # Verify arguments of the calls
        self.sync_obj.syncronize_sync.assert_has_calls([
            call(ANY, self.uid, u'res.partner', 'sync', 2, context=context),
            call(ANY, self.uid, u'res.country', 'sync', 2, context=context),
            call(ANY, self.uid, u'res.country.state', 'sync', 5, context=context),
        ])

    def test_action_sync__static_model(self):
        # Mock syncronize_sync method
        self.sync_obj.syncronize_sync = MagicMock()

        context = {
            'from_model': 'account.fiscal.position',
            'active_ids': [1]
        }
        wiz_values = {
            'odoo_id': 100,
        }
        wiz_id = self.wizard_obj.create(self.cursor, self.uid, wiz_values, context=context)
        wiz = self.wizard_obj.browse(self.cursor, self.uid, wiz_id, context=context)
        # Ensure is_static is True
        self.assertTrue(wiz.is_static)

        self.wizard_obj.action_sync(self.cursor, self.uid, [wiz_id], context=context)

        # Verify syncronize_sync was called once
        self.assertEqual(self.sync_obj.syncronize_sync.call_count, 1)

        # Verify arguments of the call
        expected_context = context.copy()
        expected_context['is_static'] = True
        expected_context['odoo_id'] = 100
        self.sync_obj.syncronize_sync.assert_called_with(
            self.cursor, self.uid, 'account.fiscal.position', 'sync', 1, context=expected_context
        )

    def test_action_sync__no_static_model_syncronize_sync(self):
        # Mock syncronize_sync method
        self.sync_obj.syncronize_sync = MagicMock()  # syncronize_sync
        self.sync_obj.syncronize = MagicMock()  # synchronize async

        self.sync_obj.sync_model_enabled_amplified = MagicMock()
        # sync_model_enabled_amplified returns (sync_enabled, auto_sync, async_enabled)
        self.sync_obj.sync_model_enabled_amplified.return_value = True, False, False

        context = {
            'from_model': 'res.partner',
            'active_ids': [1]
        }
        wiz_values = {}
        wiz_id = self.wizard_obj.create(self.cursor, self.uid, wiz_values, context=context)
        wiz = self.wizard_obj.browse(self.cursor, self.uid, wiz_id, context=context)
        # Ensure is_static is False
        self.assertFalse(wiz.is_static)

        self.wizard_obj.action_sync(self.cursor, self.uid, [wiz_id], context=context)

        # Verify syncronize_sync was called once
        self.assertEqual(self.sync_obj.syncronize_sync.call_count, 1)
        self.assertEqual(self.sync_obj.syncronize.call_count, 0)

        # Verify arguments of the call
        expected_context = context.copy()
        expected_context['is_static'] = False
        self.sync_obj.syncronize_sync.assert_called_with(
            self.cursor, self.uid, 'res.partner', 'sync', 1, context=expected_context
        )

    def test_action_sync__no_static_model_syncronize_async(self):
        # Mock syncronize_sync method
        self.sync_obj.syncronize_sync = MagicMock()  # syncronize_sync
        self.sync_obj.syncronize = MagicMock()  # synchronize async

        self.sync_obj.sync_model_enabled_amplified = MagicMock()
        # sync_model_enabled_amplified returns (sync_enabled, auto_sync, async_enabled)
        self.sync_obj.sync_model_enabled_amplified.return_value = True, False, True

        context = {
            'from_model': 'res.partner',
            'active_ids': [1]
        }
        wiz_values = {}
        wiz_id = self.wizard_obj.create(self.cursor, self.uid, wiz_values, context=context)
        wiz = self.wizard_obj.browse(self.cursor, self.uid, wiz_id, context=context)
        # Ensure is_static is False
        self.assertFalse(wiz.is_static)

        self.wizard_obj.action_sync(self.cursor, self.uid, [wiz_id], context=context)

        # Verify syncronize_sync was called once
        self.assertEqual(self.sync_obj.syncronize_sync.call_count, 0)
        self.assertEqual(self.sync_obj.syncronize.call_count, 1)

        # Verify arguments of the call
        expected_context = context.copy()
        expected_context['is_static'] = False
        self.sync_obj.syncronize.assert_called_with(
            self.cursor, self.uid, 'res.partner', 'sync', 1, context=expected_context
        )
