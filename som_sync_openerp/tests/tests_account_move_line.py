# -*- coding: utf-8 -*-
from __future__ import absolute_import

import mock

from destral import testing

from som_sync_openerp.models.odoo_exceptions import ForeingKeyNotAvailable


class TestAccountMoveLineBankStatement(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.aml_obj = self.openerp.pool.get('account.move.line')
        self.am_obj = self.openerp.pool.get('account.move')
        self.sync_obj = self.openerp.pool.get('odoo.sync')
        super(TestAccountMoveLineBankStatement, self).setUp()

    def _line(self, line_id, move_id, reconcile_id=1, partial_id=False):
        line = mock.Mock()
        line.id = line_id
        line.move_id = mock.Mock(id=move_id)
        line.reconcile_id = mock.Mock(id=reconcile_id) if reconcile_id else False
        line.reconcile_partial_id = (
            mock.Mock(id=partial_id) if partial_id else False)
        line.invoice = False
        return line

    def _classifier_context(self, liquidity_count=1, statement=False,
                            already_synced=False):
        invoice = mock.Mock(id=8, move_id=mock.Mock(id=10))
        invoice_line = self._line(1, 10)
        counterpart_line = self._line(2, 20)
        liquidity_lines = []
        for index in range(liquidity_count):
            liquidity = mock.Mock()
            liquidity.id = 100 + index
            liquidity.account_id = mock.Mock(code='572000')
            liquidity.journal_id = mock.Mock(
                id=6, company_bank_id=mock.Mock(id=3))
            liquidity.debit = 100.0
            liquidity.credit = 0.0
            liquidity.statement_id = statement
            liquidity_lines.append(liquidity)
        counterpart_move = mock.Mock(id=20, line_id=liquidity_lines)
        patches = [
            mock.patch.object(
                self.aml_obj, 'browse', return_value=[invoice_line, counterpart_line]),
            mock.patch.object(
                self.aml_obj, '_get_reconciled_invoice', return_value=invoice),
            mock.patch.object(
                self.aml_obj, '_move_is_payment_owned', return_value=False),
            mock.patch.object(
                self.aml_obj, '_amounts_match_currency_precision', return_value=True),
            mock.patch.object(self.am_obj, 'browse', return_value=counterpart_move),
            mock.patch.object(
                self.sync_obj, 'get_bank_statement_line_odoo_id',
                return_value=77 if already_synced else False),
        ]
        return patches

    def _classify_with_patches(self, patches):
        [patch.start() for patch in patches]
        try:
            return self.aml_obj._classify_reconciled_bank_statement_lines(
                self.cursor, self.uid, [1, 2])
        finally:
            for patch in reversed(patches):
                patch.stop()

    def test_classifier_accepts_one_full_invoice_payment(self):
        result = self._classify_with_patches(self._classifier_context())

        self.assertEqual(result, [100])

    def test_classifier_skips_partial_reconciliation(self):
        patches = self._classifier_context()
        partial_line = self._line(1, 10, reconcile_id=False, partial_id=9)
        patches[0] = mock.patch.object(
            self.aml_obj, 'browse', return_value=[partial_line])

        self.assertEqual(self._classify_with_patches(patches), [])

    def test_classifier_skips_multiple_invoices(self):
        patches = self._classifier_context()
        patches[1] = mock.patch.object(
            self.aml_obj, '_get_reconciled_invoice', return_value=False)

        self.assertEqual(self._classify_with_patches(patches), [])

    def test_classifier_skips_multiple_or_missing_liquidity(self):
        self.assertEqual(
            self._classify_with_patches(
                self._classifier_context(liquidity_count=0)), [])
        self.assertEqual(
            self._classify_with_patches(
                self._classifier_context(liquidity_count=2)), [])

    def test_classifier_skips_statement_origin(self):
        result = self._classify_with_patches(
            self._classifier_context(statement=mock.Mock(id=4)))

        self.assertEqual(result, [])

    def test_classifier_skips_already_synced_line(self):
        result = self._classify_with_patches(
            self._classifier_context(already_synced=True))

        self.assertEqual(result, [])

    def test_classifier_skips_payment_owned_move(self):
        patches = self._classifier_context()
        patches[2] = mock.patch.object(
            self.aml_obj, '_move_is_payment_owned', return_value=True)

        self.assertEqual(self._classify_with_patches(patches), [])

    def test_classifier_skips_journal_without_company_bank(self):
        patches = self._classifier_context()
        patches[0] = mock.patch.object(
            self.aml_obj, 'browse', return_value=[
                self._line(1, 10), self._line(2, 20)])
        counterpart_move = mock.Mock(id=20)
        liquidity = mock.Mock(
            id=100,
            account_id=mock.Mock(code='572000'),
            journal_id=mock.Mock(id=6, company_bank_id=False),
            debit=100.0,
            credit=0.0,
            statement_id=False,
        )
        counterpart_move.line_id = [liquidity]
        patches[4] = mock.patch.object(
            self.am_obj, 'browse', return_value=counterpart_move)

        self.assertEqual(self._classify_with_patches(patches), [])

    def test_classifier_skips_amount_mismatch(self):
        patches = self._classifier_context()
        patches[3] = mock.patch.object(
            self.aml_obj, '_amounts_match_currency_precision',
            return_value=False)

        self.assertEqual(self._classify_with_patches(patches), [])

    def test_manual_payload_keeps_signed_amount_and_invoice_reference(self):
        liquidity = mock.Mock()
        liquidity.id = 100
        liquidity.journal_id = mock.Mock(id=6)
        liquidity.date = '2026-01-20'
        counterpart = mock.Mock(reconcile_id=mock.Mock(id=5))
        liquidity.move_id = mock.Mock(
            date='2026-01-19', line_id=[liquidity, counterpart])
        liquidity.reconcile_id = False
        liquidity.debit = 0.0
        liquidity.credit = 125.0
        invoice = mock.Mock(id=8, number='INV/8', partner_id=mock.Mock(id=9))

        with mock.patch.object(self.aml_obj, 'browse') as mock_browse:
            mock_browse.side_effect = [liquidity, [mock.Mock()]]
            with mock.patch.object(self.aml_obj, 'search', return_value=[1, 2]):
                with mock.patch.object(
                        self.aml_obj, '_classify_reconciled_bank_statement_lines',
                        return_value=[100]):
                    with mock.patch.object(
                            self.aml_obj, '_get_reconciled_invoice',
                            return_value=invoice):
                        with mock.patch.object(
                                self.sync_obj, 'get_odoo_id_by_erp_id',
                                return_value=60):
                            with mock.patch.object(
                                    self.sync_obj, 'get_partner_odoo_id_by_erp_id',
                                    return_value=90):
                                values = self.aml_obj._get_manual_bank_statement_line_values(
                                    self.cursor, self.uid, 100)

        self.assertEqual(values, {
            'pnt_source_model': 'account.move.line',
            'pnt_erp_id': 100,
            'journal_id': 60,
            'date': '2026-01-20',
            'amount': -125.0,
            'partner_id': 90,
            'payment_ref': '[FACTURA] INV/8',
        })

    def test_enqueue_deduplicates_eligible_liquidity_ids(self):
        liquidity = mock.Mock(journal_id=mock.Mock(id=6))
        with mock.patch.object(
                self.aml_obj, '_classify_reconciled_bank_statement_lines',
                return_value=[100, 100]):
            with mock.patch.object(self.aml_obj, 'browse', return_value=liquidity):
                with mock.patch.object(
                        self.sync_obj, 'prepare_bank_statement_line_marker'):
                    with mock.patch.object(
                            self.sync_obj, 'get_odoo_id_by_erp_id', return_value=60):
                        with mock.patch.object(
                                self.aml_obj,
                                'sync_manual_bank_statement_line') as mock_sync:
                            self.aml_obj._enqueue_reconciled_bank_statement_lines(
                                self.cursor, self.uid, [1, 2])

        mock_sync.assert_called_once_with(
            self.cursor, self.uid, 100, context={})

    def test_enqueue_persists_pending_marker_without_journal_mapping(self):
        liquidity = mock.Mock(journal_id=mock.Mock(id=6))
        with mock.patch.object(
                self.aml_obj, '_classify_reconciled_bank_statement_lines',
                return_value=[100]):
            with mock.patch.object(self.aml_obj, 'browse', return_value=liquidity):
                with mock.patch.object(
                        self.sync_obj,
                        'prepare_bank_statement_line_marker') as mock_prepare:
                    with mock.patch.object(
                            self.sync_obj, 'get_odoo_id_by_erp_id',
                            return_value=False):
                        with mock.patch.object(
                                self.aml_obj,
                                'sync_manual_bank_statement_line') as mock_sync:
                            self.aml_obj._enqueue_reconciled_bank_statement_lines(
                                self.cursor, self.uid, [1, 2])

        mock_prepare.assert_called_once_with(
            self.cursor, self.uid, 'account.move.line', 100, context={})
        mock_sync.assert_not_called()

    def test_manual_sync_keeps_marker_pending_when_mapping_is_missing(self):
        with mock.patch.object(
                self.aml_obj, '_get_manual_bank_statement_line_values',
                side_effect=ForeingKeyNotAvailable('account.journal,6')):
            result = self.aml_obj._sync_manual_bank_statement_line(
                self.cursor, self.uid, 100)

        self.assertFalse(result)

    def test_norma57_context_skips_manual_payment_sync(self):
        self.assertTrue(self.aml_obj._skip_bank_statement_line_payment_sync({
            'skip_bank_statement_line_payment_sync': True,
        }))
        self.assertTrue(self.aml_obj._skip_bank_statement_line_payment_sync({
            'norma_57_name': 'N57 legacy context',
        }))
        self.assertFalse(
            self.aml_obj._skip_bank_statement_line_payment_sync({}))
