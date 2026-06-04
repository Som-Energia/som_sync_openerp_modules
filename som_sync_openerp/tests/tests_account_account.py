# -*- coding: utf-8 -*-
from destral import testing


class TestAccountAccount(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.account_obj = self.openerp.pool.get("account.account")
        self.imd_obj = self.openerp.pool.get("ir.model.data")
        super(TestAccountAccount, self).setUp()

    def test_get_endpoint_suffix(self):
        account_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "account", "account_unpaid"
        )[1]

        suffix = self.account_obj.get_endpoint_suffix(self.cursor, self.uid, account_id)

        self.assertEqual(suffix, '412345')

    def test_ensure_demo_account_iva__reuses_existing_account(self):
        before_count = len(self.account_obj.search(
            self.cursor, self.uid, [('code', '=', '475600'), ('company_id', '=', 1)]
        ))

        ensured_id = self.account_obj.ensure_demo_account_iva(
            self.cursor, self.uid, context={}
        )

        account_ids = self.account_obj.search(
            self.cursor, self.uid, [('code', '=', '475600'), ('company_id', '=', 1)]
        )

        self.assertTrue(ensured_id in account_ids)
        self.assertEqual(len(account_ids), before_count)

    def test_ensure_demo_account_iva__creates_missing_account(self):
        account_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'account_account_iva'
        )[1]
        imd_id = self.imd_obj._get_id(
            self.cursor, self.uid, 'som_sync_openerp', 'account_account_iva'
        )
        self.imd_obj.unlink(self.cursor, self.uid, [imd_id])
        self.account_obj.unlink(self.cursor, self.uid, [account_id])

        ensured_id = self.account_obj.ensure_demo_account_iva(
            self.cursor, self.uid, context={}
        )
        xml_account_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'account_account_iva'
        )[1]
        account = self.account_obj.read(
            self.cursor, self.uid, ensured_id,
            ['name', 'code', 'company_id', 'currency_mode', 'type']
        )

        self.assertEqual(xml_account_id, ensured_id)
        self.assertEqual(account['name'], 'Compte IVA per linia IESE')
        self.assertEqual(account['code'], '475600')
        self.assertEqual(account['company_id'][0], 1)
        self.assertEqual(account['currency_mode'], 'current')
        self.assertEqual(account['type'], 'other')
