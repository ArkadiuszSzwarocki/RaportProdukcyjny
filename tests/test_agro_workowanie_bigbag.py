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

    def test_lookup_bigbag_by_exact_sscc(self):
        with patch('app.services.agro_workowanie_bigbag_service.get_db_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_conn.return_value.cursor.return_value = mock_cursor
            mock_cursor.fetchone.return_value = {
                'id': 2253,
                'nr_palety': 'PSD000001790147129443',
                'nazwa': 'MLECZNA PYCHA BRĄZOWA',
                'stan_magazynowy': 732.0,
                'lokalizacja': 'MP01',
                'nr_partii': 'BRAK',
                'data_produkcji': None,
                'data_przydatnosci': None,
                'is_blocked': 0,
                'typ_palety': 'Wyrób Gotowy',
                'linia': 'PSD',
                'table_name': 'magazyn_palety',
                'qty_column': 'waga_netto'
            }

            result = AgroWorkowanieBigBagService.lookup_bigbag('PSD000001790147129443', linia='AGRO')
            self.assertIsNotNone(result)
            self.assertEqual(result['id'], 2253)
            self.assertFalse(result['is_blocked'])
            self.assertEqual(result['nazwa'], 'MLECZNA PYCHA BRĄZOWA')

    def test_lookup_bigbag_by_numeric_id(self):
        with patch('app.services.agro_workowanie_bigbag_service.get_db_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_conn.return_value.cursor.return_value = mock_cursor
            mock_cursor.fetchone.side_effect = [
                None,  # exact nr_palety agro
                None,  # exact nr_palety psd
                None,  # exact nr_palety surowce agro
                None,  # exact nr_palety surowce psd
                {      # id match in magazyn_palety
                    'id': 2255,
                    'nr_palety': 'PSD000001790147180360',
                    'nazwa': 'MLECZNA PYCHA BRĄZOWA',
                    'stan_magazynowy': 1010.0,
                    'lokalizacja': 'MP01',
                    'nr_partii': 'BRAK',
                    'data_produkcji': None,
                    'data_przydatnosci': None,
                    'is_blocked': 0,
                    'typ_palety': 'Wyrób Gotowy',
                    'linia': 'PSD',
                    'table_name': 'magazyn_palety',
                    'qty_column': 'waga_netto'
                }
            ]

            result = AgroWorkowanieBigBagService.lookup_bigbag('2255', linia='AGRO')
            self.assertIsNotNone(result)
            self.assertEqual(result['id'], 2255)
            self.assertFalse(result['is_blocked'])


if __name__ == '__main__':
    unittest.main()

