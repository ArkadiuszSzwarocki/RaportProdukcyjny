"""Unit tests for pallet splitting and partial moves with SSCC generation and mother history inheritance."""

import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.services.magazyn_dostawy.pallet_split_service import PalletSplitService
from app.services.warehouse_v2_service import WarehouseV2Service


class TestPalletSplitServiceHistoryInheritance(unittest.TestCase):
    """Weryfikacja dziedziczenia historii z palety matki w PalletSplitService."""

    def test_split_inventory_copies_mother_history_and_assigns_new_sscc(self):
        mother_pallet = {
            'id': 101,
            'nr_palety': 'SUR_MOTHER_101',
            'nazwa': 'Mąka Pszenna Typ 500',
            'stan_magazynowy': 100.0,
            'lokalizacja': 'R010101',
            'data_produkcji': datetime(2026, 1, 10),
            'termin_przydatnosci': datetime(2026, 12, 31),
            'nr_partii': 'LOT-2026-99',
        }

        # Mock historii palety matki
        mother_history_records = [
            {
                'linia': 'AGRO',
                'typ_palety': 'surowiec',
                'akcja': 'PRZYJECIE_DOSTAWY',
                'lokalizacja_zrodlowa': None,
                'lokalizacja_docelowa': 'RAMPA',
                'komentarz': 'Przyjęcie dostawy PZ/2026/01',
                'user_login': 'magazynier1',
                'data_ruchu': datetime(2026, 1, 10, 8, 0, 0),
            },
            {
                'linia': 'AGRO',
                'typ_palety': 'surowiec',
                'akcja': 'PRZESUNIECIE',
                'lokalizacja_zrodlowa': 'RAMPA',
                'lokalizacja_docelowa': 'R010101',
                'komentarz': 'Przesunięcie na regał',
                'user_login': 'magazynier1',
                'data_ruchu': datetime(2026, 1, 10, 9, 30, 0),
            },
        ]

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.lastrowid = 202

        # Gdy _copy_mother_history wykonuje SELECT z palety_historia
        mock_cursor.fetchall.return_value = mother_history_records

        executed_sql = []
        def capture_execute(sql, params=None):
            executed_sql.append((sql, params))

        mock_cursor.execute.side_effect = capture_execute

        new_generated_sscc = 'SUR_CHILD_2026_000202'
        with patch.object(PalletSplitService, 'find_by_id', return_value=(mother_pallet, 'AGRO')), \
             patch('app.services.magazyn_dostawy.pallet_split_service.get_db_connection', return_value=mock_conn), \
             patch('app.services.magazyn_dostawy.pallet_split_service.generate_pallet_id', return_value=new_generated_sscc):

            ok, msg, res = PalletSplitService.split_pallet(
                101,
                'surowiec',
                30.0,
                'jan_kowalski',
                'AGRO'
            )

        self.assertTrue(ok, f"Split failed: {msg}")
        self.assertEqual(res['nr_palety'], new_generated_sscc)
        self.assertEqual(res['waga'], 30.0)
        self.assertEqual(res['mother_new_weight'], 70.0)

        # Sprawdzenie czy w palety_historia pojawiły się wpisy:
        # 2 skopiowane z matki (ze starym data_ruchu i nowym SSCC)
        # 1 PODZIAL_ODJECIE na matce
        # 1 PODZIAL_UTWORZENIE na potomku
        historia_inserts = [
            (sql, params) for sql, params in executed_sql
            if 'INSERT INTO palety_historia' in sql
        ]
        self.assertEqual(len(historia_inserts), 4, f"Oczekiwano 4 wpisów do historii, otrzymano {len(historia_inserts)}")

        # Sprawdź czy skopiowane wpisy mają new_pallet_id (202) oraz new_sscc
        copied_history = historia_inserts[:2]
        for sql, params in copied_history:
            self.assertEqual(params[0], 202)  # paleta_id
            self.assertEqual(params[1], new_generated_sscc)  # nr_palety

        # Sprawdź wpis podziału na matce
        mother_split_log = historia_inserts[2]
        self.assertEqual(mother_split_log[1][0], 101)  # mother_id
        self.assertEqual(mother_split_log[1][1], 'SUR_MOTHER_101')  # mother_sscc
        self.assertEqual(mother_split_log[1][4], 'PODZIAL_ODJECIE')

        # Sprawdź wpis podziału na potomku
        child_split_log = historia_inserts[3]
        self.assertEqual(child_split_log[1][0], 202)  # child_id
        self.assertEqual(child_split_log[1][1], new_generated_sscc)  # new_sscc
        self.assertEqual(child_split_log[1][4], 'PODZIAL_UTWORZENIE')


class TestWarehouseV2PartialMove(unittest.TestCase):
    """Weryfikacja częściowego przesunięcia (np. 30 kg z 40 kg) w WarehouseV2Service."""

    def test_partial_move_creates_child_pallet_with_new_sscc_and_copies_history(self):
        mother_row = {
            'id': 50,
            'nr_palety': 'SUR_MATKA_50',
            'stan_magazynowy': 40.0,
            'nazwa': 'Cukier puder',
            'lokalizacja': 'R020101',
            'is_blocked': 0,
        }

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor_dict = MagicMock()
        mock_cursor_dict.fetchone.return_value = mother_row

        # Historia palety matki
        mother_history_records = [
            {
                'linia': 'PSD',
                'typ_palety': 'surowiec',
                'akcja': 'PRZYJECIE_DOSTAWY',
                'lokalizacja_zrodlowa': None,
                'lokalizacja_docelowa': 'R020101',
                'komentarz': 'Dostawa pierwotna',
                'user_login': 'kierowca',
                'data_ruchu': datetime(2026, 2, 1, 10, 0, 0),
            }
        ]

        def dict_fetchall():
            return list(mother_history_records)

        mock_cursor_dict.fetchall.side_effect = dict_fetchall

        def cursor_factory(dictionary=False):
            if dictionary:
                cur = MagicMock()
                cur.fetchone.return_value = mother_row
                cur.fetchall.return_value = list(mother_history_records)
                return cur
            return mock_cursor

        mock_conn.cursor = cursor_factory
        mock_cursor.lastrowid = 88

        executed_sql = []
        def capture_exec(sql, params=None):
            executed_sql.append((sql, params))
        mock_cursor.execute.side_effect = capture_exec

        new_sscc_gen = 'SUR_POTOMEK_88'

        with patch('app.services.warehouse_v2_service.get_db_connection', return_value=mock_conn), \
             patch('app.utils.pallet_id.generate_pallet_id', return_value=new_sscc_gen), \
             patch('app.services.magazyn_dostawy.delivery_queries.DeliveryQueries.is_pallet_in_pending_transfer', return_value=(False, None)), \
             patch('app.utils.location_validator.check_rack_location_availability', return_value=(True, '')):

            res = WarehouseV2Service.move_pallet(
                pallet_id=50,
                pallet_type='Surowiec',
                new_location='R030101',
                worker_login='jan_kowalski',
                linia='PSD',
                amount_to_move=30.0,
            )
            ok = res[0]
            msg = res[1]
            split_info = res[2] if len(res) > 2 else None

        self.assertTrue(ok, f"Przesunięcie zakończone błędem: {msg}")
        self.assertIsNotNone(split_info)
        self.assertTrue(split_info.get('is_split'))
        self.assertEqual(split_info.get('new_sscc'), new_sscc_gen)

        # Sprawdzenie UPDATE stanu matki (40 - 30 = 10 kg)
        update_mother = [
            params for sql, params in executed_sql
            if 'UPDATE' in sql and 'stan_magazynowy' in sql
        ]
        self.assertTrue(len(update_mother) >= 1)
        self.assertEqual(update_mother[0][0], 10.0)  # pozostało 10 kg
        self.assertEqual(update_mother[0][1], 50)    # mother_id

        # Sprawdzenie INSERT nowej palety potomnej
        insert_child = [
            (sql, params) for sql, params in executed_sql
            if 'INSERT INTO magazyn_surowce' in sql
        ]
        self.assertTrue(len(insert_child) >= 1)

        # Sprawdzenie kopiowania historii do nowej palety potomnej
        historia_inserts = [
            (sql, params) for sql, params in executed_sql
            if 'INSERT INTO palety_historia' in sql
        ]
        # Oczekujemy: 1 skopiowany rekord + 1 PODZIAL_PALETY na nowej + 1 PODZIAL_ODJECIE na matce
        self.assertEqual(len(historia_inserts), 3)

        # 1. Skopiowany wpis ma new_pallet_id (88) i new_sscc
        self.assertEqual(historia_inserts[0][1][0], 88)
        self.assertEqual(historia_inserts[0][1][1], new_sscc_gen)

        # 2. PODZIAL_PALETY w params[4]
        self.assertEqual(historia_inserts[1][1][4], 'PODZIAL_PALETY')
        self.assertEqual(historia_inserts[1][1][0], 88)
        self.assertEqual(historia_inserts[1][1][1], new_sscc_gen)

        # 3. PODZIAL_ODJECIE (w SQL 'PODZIAL_ODJECIE' to literał)
        self.assertIn("'PODZIAL_ODJECIE'", historia_inserts[2][0])
        self.assertEqual(historia_inserts[2][1][0], 50)
        self.assertEqual(historia_inserts[2][1][1], 'SUR_MATKA_50')


if __name__ == '__main__':
    unittest.main()
