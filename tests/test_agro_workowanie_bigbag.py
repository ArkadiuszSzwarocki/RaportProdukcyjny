import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock
from app.services.agro_workowanie_bigbag_service import AgroWorkowanieBigBagService


class TestAgroWorkowanieBigBag(unittest.TestCase):
    def test_lookup_bigbag_not_found(self):
        with patch('app.services.agro_workowanie_bigbag_service.get_db_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_conn.return_value.cursor.return_value = mock_cursor
            mock_cursor.fetchone.return_value = None

            result = AgroWorkowanieBigBagService.lookup_bigbag('NON_EXISTING')
            self.assertIsNone(result)

    def test_get_plan_bigbag_settlement_empty(self):
        with patch('app.services.agro_workowanie_bigbag_service.get_db_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_conn.return_value.cursor.return_value = mock_cursor
            mock_cursor.fetchall.side_effect = [[], []]

            settlement = AgroWorkowanieBigBagService.get_plan_bigbag_settlement(999)
            self.assertEqual(settlement['total_bigbag_kg'], 0.0)
            self.assertEqual(settlement['total_packed_kg'], 0.0)
            self.assertEqual(settlement['bilans_kg'], 0.0)
            self.assertFalse(settlement['has_bigbags'])

    def test_get_plan_bigbag_settlement_calculated(self):
        with patch('app.services.agro_workowanie_bigbag_service.get_db_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_conn.return_value.cursor.return_value = mock_cursor

            fake_bigbags = [
                {'id': 1, 'nr_palety': 'BB001', 'nazwa_produktu': 'Mix A', 'waga_kg': 1000.0, 'created_at': datetime.now()},
                {'id': 2, 'nr_palety': 'BB002', 'nazwa_produktu': 'Mix A', 'waga_kg': 1000.0, 'created_at': datetime.now()}
            ]
            fake_pallets = [
                {'id': 10, 'nr_palety': 'PAL01', 'waga': 990.0},
                {'id': 11, 'nr_palety': 'PAL02', 'waga': 980.0}
            ]
            mock_cursor.fetchall.side_effect = [fake_bigbags, fake_pallets]

            settlement = AgroWorkowanieBigBagService.get_plan_bigbag_settlement(123)
            self.assertEqual(settlement['total_bigbag_kg'], 2000.0)
            self.assertEqual(settlement['total_packed_kg'], 1970.0)
            self.assertEqual(settlement['bilans_kg'], -30.0)
            self.assertEqual(settlement['loss_pct'], -1.5)
            self.assertEqual(settlement['pallets_count'], 2)
            self.assertTrue(settlement['has_bigbags'])


if __name__ == '__main__':
    unittest.main()
