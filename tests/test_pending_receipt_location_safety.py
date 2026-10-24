"""Pending views and reservations must not move physical stock."""
import unittest
from unittest.mock import MagicMock, patch

from app.services.magazyn_dostawy.delivery_queries import DeliveryQueries
from app.services.magazyn_dostawy.commands.pallet_lock_manager import PalletLockManager


class PendingReceiptLocationSafety(unittest.TestCase):
    def test_pending_view_never_runs_stock_reconciliation(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value
        cursor.fetchall.return_value = []
        with patch('app.services.magazyn_dostawy.delivery_queries.get_db_connection', return_value=conn), patch.object(DeliveryQueries, 'get_pending_production_pallets', return_value=[]), patch.object(DeliveryQueries, 'sync_pending_transfers_blocked_state') as sync:
            self.assertEqual(DeliveryQueries.get_oczekujace('ALL'), {'dostawy': [], 'wg': []})
        sync.assert_not_called()
        conn.commit.assert_not_called()
        self.assertTrue(all(call.args[0].strip().startswith('SELECT') for call in cursor.execute.call_args_list))

    def test_processed_pallet_is_never_reserved_again(self):
        for flag in ('accepted', 'rejected', 'putaway_confirmed_at'):
            with self.subTest(flag=flag):
                cursor = MagicMock()
                PalletLockManager.set_pallets_blocked(cursor, [{'nr_palety': 'SUR-RECEIVED', flag: True}], 1)
                cursor.execute.assert_not_called()

    def test_reservation_uses_sscc_and_preserves_physical_location(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [{'id': 4212, 'nr_palety': 'SUR-4212', 'lokalizacja': 'MS01'}]
        with patch('app.core.logistics_permissions.logistics_stock_write_allowed', return_value=True), patch.object(PalletLockManager, 'has_active_osip_transfer', return_value=False):
            PalletLockManager.set_pallets_blocked(cursor, [{'sourcePalletId': 110, 'nr_palety': 'SUR-4212', 'sourceTable': 'magazyn_surowce'}], 1)
        select, update = cursor.execute.call_args_list
        self.assertIn('UPPER(nr_palety) = %s', select.args[0])
        self.assertEqual(select.args[1], ('SUR-4212',))
        self.assertEqual(update.args, ('UPDATE magazyn_surowce SET is_blocked = %s WHERE id = %s', (1, 4212)))

    def test_untyped_numeric_id_cannot_touch_unrelated_stock(self):
        cursor = MagicMock()
        with self.assertRaises(ValueError):
            PalletLockManager.set_pallets_blocked(cursor, [{'sourcePalletId': 110}], 1)
        cursor.execute.assert_not_called()


if __name__ == '__main__':
    unittest.main()
