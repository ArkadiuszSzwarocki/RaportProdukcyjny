"""Tests for cleaning pallet SSCC assignment and mother history copying."""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
import json
from flask import Flask, session

from app.services.warehouse_pallet_service import WarehousePalletService
from app.repositories.warehouse_pallet_repository import WarehousePalletRepository
from app.utils.pallet_label import prepare_pallet_label_data


class TestCleaningPalletHistory(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'test-secret'

    def test_find_cleaning_sscc(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = ('  SUR-MOTH-999  ',)

        result = WarehousePalletRepository.find_cleaning_sscc(10, 5, 'PSD', conn=mock_conn)
        self.assertEqual(result, 'SUR-MOTH-999')

        mock_cur.fetchone.return_value = ('', )
        result_empty = WarehousePalletRepository.find_cleaning_sscc(10, 5, 'PSD', conn=mock_conn)
        self.assertIsNone(result_empty)

    @patch('app.services.warehouse_pallet_service.get_db_connection')
    @patch('app.services.warehouse_pallet_service.generate_pallet_id', return_value='NEW-SSCC-001')
    @patch('app.services.warehouse_pallet_service.WarehouseMovementLedgerRepository.record_movement')
    @patch('app.repositories.warehouse_pallet_repository.WarehousePalletRepository.get_plan_info')
    def test_dodaj_palete_assigns_new_sscc_for_cleaning(self, mock_plan_info, mock_record_mv, mock_gen_id, mock_get_conn):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_get_conn.return_value = mock_conn

        mock_plan_info.return_value = {
            'tonaz_planowany': 1000,
            'sekcja': 'Czyszczenie',
            'produkt': 'Czyszczenie',
            'data_planu': '2026-09-08',
            'typ_produkcji': 'Worki',
            'status': 'w toku',
            'zasyp_id': 5,
            'data_produkcji': '2026-09-08'
        }

        mock_cur.fetchone.side_effect = [
            (1,),  # count for lp
            ('nr_palety_lp',),  # show columns
        ]

        with patch('app.repositories.warehouse_pallet_repository.WarehousePalletRepository.find_reserved_pallet', return_value=None):
            with patch('app.repositories.warehouse_pallet_repository.WarehousePalletRepository.find_cleaning_sscc', return_value='SUR-MOTH-999'):
                with patch('app.repositories.warehouse_pallet_repository.WarehousePalletRepository.insert_new_pallet', return_value=123) as mock_ins:
                    with self.app.test_request_context():
                        resp = WarehousePalletService.dodaj_palete(
                            plan_id=1,
                            linia='PSD',
                            waga_palety='1000',
                            nr_plomby='',
                            data_produkcji='2026-09-08',
                            printer_ip=None,
                            printer_name=None,
                            user_login='Tester',
                            app_obj=self.app,
                            is_ajax=True,
                            safe_return_url=None
                        )

        self.assertTrue(resp[0])
        mock_ins.assert_called_once()
        self.assertEqual(mock_ins.call_args[1]['nr_palety'], 'NEW-SSCC-001')

        hist_calls = [c for c in mock_cur.execute.call_args_list if 'INSERT INTO palety_historia' in c[0][0]]
        self.assertTrue(len(hist_calls) > 0)
        hist_sql, hist_args = hist_calls[0][0]
        self.assertEqual(hist_args[1], 'NEW-SSCC-001')
        self.assertIn('Paleta matka: SUR-MOTH-999', hist_args[3])

    @patch('app.services.warehouse_pallet_service.get_db_connection')
    def test_potwierdz_palete_cleaning_copies_mother_history_and_sets_delivery(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_get_conn.return_value = mock_conn

        # Setup fetchone calls for potwierdz_palete:
        # 1: tara query
        # 2: declared waga query
        # 3: check_pal (plan_id, nr_palety, waga, tara, waga_brutto, status)
        # 4: plan_info (data_planu, produkt, data_produkcji)
        # 5: mp_id (plan Magazyn)
        # 6: skan_sscc query (mother pallet)
        mock_cur.fetchone.side_effect = [
            (25,),                                         # tara
            (1000,),                                       # declared waga
            (10, 'do_przyjecia', 1000, 'NEW-CHILD-777', None), # check_pal (plan_id, status, stored_netto, nr_palety, nr_plomby)
            ('2026-09-08', 'Czyszczenie', '2026-09-08'),    # plan_info
            None,                                          # mp_id for Magazyn
            ('SUR-MOTHER-123',),                           # skan_sscc query
        ]

        # Mother history rows from palety_historia
        mock_cur.fetchall.return_value = [
            ('PSD', 'surowiec', 'DOSTAWA_PRZYJECIE', None, 'MS01', 'Przyjęcie surowca', 'Kierowca', datetime(2026, 9, 1)),
            ('PSD', 'surowiec', 'PRZESUNIECIE', 'MS01', 'CZ01', 'Przeniesienie do czyszczenia', 'Operator', datetime(2026, 9, 8)),
        ]
        mock_cur.rowcount = 1

        with patch('app.utils.pallet_label.lookup_raw_material_details_by_sscc', return_value={
            'nr_partii': 'PARTIA-FLOUR-99',
            'data_produkcji': '2026-09-01',
            'data_przydatnosci': '2027-09-01'
        }):
            with self.app.test_request_context(method='POST', data={
                'waga_netto': '1000',
                'waga_brutto': '1025',
                'tara': '25',
                'lokalizacja': 'BF_MS01',
                'data_produkcji': '2026-09-08'
            }):
                session['rola'] = 'admin'
                ok, msg, res = WarehousePalletService.potwierdz_palete(
                    paleta_id=100,
                    linia='PSD',
                    user_login='Janusz',
                    app_obj=self.app,
                    update_paleta_workowanie=None,
                    update_paleta_magazyn=None,
                    is_ajax=True,
                    safe_return_url=None
                )

        self.assertTrue(ok)

        # 1. Check delivery insertion in magazyn_dostawy
        dostawa_calls = [c for c in mock_cur.execute.call_args_list if 'INSERT INTO magazyn_dostawy' in c[0][0]]
        self.assertEqual(len(dostawa_calls), 1)
        dostawa_sql, dostawa_args = dostawa_calls[0][0]
        items_str = dostawa_args[5]
        items = json.loads(items_str)
        self.assertEqual(items[0]['nr_palety'], 'NEW-CHILD-777')
        self.assertEqual(items[0]['sourcePalletNo'], 'SUR-MOTHER-123')
        self.assertEqual(items[0]['nr_partii'], 'PARTIA-FLOUR-99')

        # 2. Check palety_historia: copied entries + PRZEKLASYFIKOWANIE + PRZEKLASYFIKOWANIE_POTOMNA
        hist_calls = [c for c in mock_cur.execute.call_args_list if 'INSERT INTO palety_historia' in c[0][0]]
        self.assertGreaterEqual(len(hist_calls), 4)

        # Copied items should have child SSCC NEW-CHILD-777
        copied_args = [c[0][1] for c in hist_calls if 'Przyjęcie surowca' in str(c[0][1])]
        self.assertEqual(len(copied_args), 1)
        self.assertEqual(copied_args[0][1], 'NEW-CHILD-777')

        # Reclassification event on new pallet
        reclass_calls = [c for c in hist_calls if 'PRZEKLASYFIKOWANIE' in c[0][0] and 'PRZEKLASYFIKOWANIE_POTOMNA' not in c[0][0]]
        self.assertEqual(len(reclass_calls), 1)
        reclass_sql, reclass_args = reclass_calls[0][0]
        self.assertEqual(reclass_args[1], 'NEW-CHILD-777')
        self.assertIn('z palety matki SUR-MOTHER-123', reclass_args[4])

        # Mother pallet link event
        mother_link_calls = [c for c in hist_calls if 'PRZEKLASYFIKOWANIE_POTOMNA' in c[0][0]]
        self.assertEqual(len(mother_link_calls), 1)
        m_link_sql, mother_link_args = mother_link_calls[0][0]
        self.assertEqual(mother_link_args[0], 'SUR-MOTHER-123')
        self.assertIn('Nowa paleta potomna: NEW-CHILD-777', mother_link_args[2])

    def test_prepare_pallet_label_data_for_cleaning(self):
        mock_cur = MagicMock()
        mock_cur.fetchone.side_effect = [
            ('nr_palety_lp',),         # SHOW COLUMNS nr_palety_lp
            ('nr_partii',),             # SHOW COLUMNS nr_partii
            ('termin_przydatnosci',),   # SHOW COLUMNS termin_przydatnosci
            None,                       # attempt 1 from magazyn_palety
            (50, 1000, 'Czyszczenie', datetime(2026, 9, 8), 'CHILD-SSCC-111', None, 1, None, None, None), # pw_row
            (1000,),                    # cumulative_paleta_waga
            (5,),                       # zasyp_id from plan
            ('SUR-MOTHER-555',),        # skan_sscc query
        ]

        with patch('app.utils.pallet_label.lookup_raw_material_details_by_sscc') as mock_lookup:
            mock_lookup.return_value = {
                'nr_partii': 'LOT-FLOUR-888',
                'data_produkcji': datetime(2026, 8, 20),
                'data_przydatnosci': datetime(2027, 8, 20)
            }
            label = prepare_pallet_label_data(mock_cur, 100, linia='PSD', source_table='workowanie')

            mock_lookup.assert_called_with(mock_cur, 'SUR-MOTHER-555')
            self.assertIsNotNone(label)
            self.assertEqual(label['nrPalety'], 'CHILD-SSCC-111')
            self.assertEqual(label['nazwa'], 'Mąka mix do Lnu')
            self.assertEqual(label['partia'], 'LOT-FLOUR-888')
            self.assertEqual(label['data_produkcji'], '2026-08-20')
            self.assertTrue(label['is_surowiec'])


if __name__ == '__main__':
    unittest.main()
