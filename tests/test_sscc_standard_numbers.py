import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime

from app.utils.pallet_id import is_valid_pallet_id, generate_pallet_id
from app.services.print_server import PrintServer
from app.services.folio_service import FolioService
from app.services.scanner_service import ScannerService


class TestStandardSSCCGeneration(unittest.TestCase):
    """Weryfikacja generowania i druku wyłącznie standardowych numerów SSCC (SUR/OPK + 18 cyfr)."""

    def test_pallet_id_validity(self):
        # Poprawne numery SSCC
        self.assertTrue(is_valid_pallet_id('SUR000001783944785565'))
        self.assertTrue(is_valid_pallet_id('OPK000001789128218508'))
        self.assertTrue(is_valid_pallet_id('AGR000001789128650397'))
        self.assertTrue(is_valid_pallet_id('PSD000001788437208834'))

        # Niepoprawne / zastępcze numery, które NIE MOGĄ być traktowane jako standardowy SSCC
        self.assertFalse(is_valid_pallet_id('SUR-1123'))
        self.assertFalse(is_valid_pallet_id('OPK-137'))
        self.assertFalse(is_valid_pallet_id('DOD-42'))
        self.assertFalse(is_valid_pallet_id(''))
        self.assertFalse(is_valid_pallet_id(None))

    def test_print_pallet_label_replaces_placeholder_with_standard_sscc(self):
        """Drukarka etykiet nigdy nie drukuje SUR-1123 ani OPK-137, tylko standardowy SSCC."""
        server = PrintServer()

        # Próba wydruku z dziwnym numerem SUR-1123
        label_data_sur = {
            'id': 1123,
            'nr_palety': 'SUR-1123',
            'nazwa': 'Lactose',
            'ilosc': 150.0,
            'zbiornik': 'MZ10',
            'linia': 'AGRO'
        }
        with patch('app.db.get_db_connection') as mock_conn:
            zpl = server.build_pallet_label_zpl(label_data_sur)

        self.assertNotIn('SUR-1123', zpl)
        self.assertIn('SUROWIEC -> MZ10', zpl)
        # Wygenerowany numer SSCC musi być standardowy
        new_sscc = label_data_sur['nr_palety']
        self.assertTrue(is_valid_pallet_id(new_sscc))
        self.assertTrue(new_sscc.startswith('SUR'))
        self.assertIn(f"^FDQA,{new_sscc}^FS", zpl)

        # Próba wydruku z dziwnym numerem OPK-137
        label_data_opk = {
            'id': 137,
            'nr_palety': 'OPK-137',
            'nazwa': 'Polmlek Czerwony',
            'ilosc': 536.0,
            'linia': 'AGRO'
        }
        with patch('app.db.get_db_connection') as mock_conn:
            zpl_opk = server.build_pallet_label_zpl(label_data_opk)

        self.assertNotIn('OPK-137', zpl_opk)
        new_opk_sscc = label_data_opk['nr_palety']
        self.assertTrue(is_valid_pallet_id(new_opk_sscc))
        self.assertTrue(new_opk_sscc.startswith('OPK'))
        self.assertIn(f"^FDQA,{new_opk_sscc}^FS", zpl_opk)

    def test_dispatch_to_production_preserves_or_creates_standard_sscc(self):
        """Wydanie na produkcję (zasyp MZ10) zwraca i zapisuje standardowy SSCC, a nie SUR-id."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur

        mock_cur.fetchone.side_effect = [
            # 1. SELECT z table_surowce
            {
                'id': 1123,
                'nr_palety': 'SUR000001783944785565',
                'nazwa': 'Lactose',
                'stan_magazynowy': 1000.0,
                'lokalizacja': 'R010303',
                'is_blocked': 0,
                'nr_partii': '0412026',
                'data_produkcji': datetime(2026, 2, 10),
                'data_przydatnosci': datetime(2028, 2, 10),
            },
            # 2. SELECT stan_magazynowy po UPDATE
            {'stan_magazynowy': 850.0}
        ]

        with patch('app.services.scanner_service.get_db_connection', return_value=mock_conn), \
             patch('app.services.tank_validation_service.TankValidationService.validate_tank_material', return_value=(True, '')):

            ok, msg, extra = ScannerService.dispatch_to_production(
                surowiec_id=1123,
                ilosc=150.0,
                worker_login='test_worker',
                linia='AGRO',
                zbiornik='MZ10'
            )

        self.assertTrue(ok)
        self.assertEqual(extra['nr_palety'], 'SUR000001783944785565')
        self.assertNotEqual(extra['nr_palety'], 'SUR-1123')


if __name__ == '__main__':
    unittest.main()
