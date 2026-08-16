"""Tests for PalletSplitService."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.services.magazyn_dostawy.pallet_split_service import PalletSplitService


class TestFindBySscc:
    def test_returns_none_for_empty_sscc(self):
        assert PalletSplitService.find_by_sscc('') is None
        assert PalletSplitService.find_by_sscc('   ') is None

    def test_returns_pallet_when_found(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [None, {'id': 5, 'nr_palety': 'AGR001', 'source': 'magazyn'}]

        with patch('app.services.magazyn_dostawy.pallet_split_service.get_db_connection', return_value=mock_conn):
            result = PalletSplitService.find_by_sscc('AGR001')

        assert result['id'] == 5
        assert result['source'] == 'magazyn'


class TestSplitPalletValidation:
    def test_rejects_invalid_input(self):
        ok, msg, result = PalletSplitService.split_pallet(0, 'magazyn', 10)
        assert ok is False
        assert 'Błędne dane' in msg
        assert result is None

    def test_rejects_missing_mother(self):
        with patch.object(PalletSplitService, 'find_by_id', return_value=(None, None)):
            ok, msg, result = PalletSplitService.split_pallet(99, 'magazyn', 10)

        assert ok is False
        assert 'Nie znaleziono palety bazowej' in msg
        assert result is None

    def test_rejects_weight_greater_than_stock(self):
        mother = {'id': 1, 'nr_palety': 'PSD123', 'waga_netto': 100}
        with patch.object(PalletSplitService, 'find_by_id', return_value=(mother, 'PSD')):
            ok, msg, result = PalletSplitService.split_pallet(1, 'magazyn', 100)

        assert ok is False
        assert 'równa lub większa' in msg
        assert result is None


class TestSplitInventory:
    def test_splits_surowiec_and_logs_history(self):
        mother = {
            'id': 10,
            'nr_palety': 'SUR001',
            'nazwa': 'Pszenica',
            'stan_magazynowy': 1000,
            'lokalizacja': 'MGW01',
            'data_produkcji': datetime(2026, 1, 1),
            'termin_przydatnosci': datetime(2027, 1, 1),
            'nr_partii': 'BATCH1',
            'certyfikat': 'CERT',
        }

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.lastrowid = 42

        executed_sql = []

        def capture_execute(sql, params=None):
            executed_sql.append((sql, params))

        mock_cursor.execute.side_effect = capture_execute

        with patch.object(PalletSplitService, 'find_by_id', return_value=(mother, 'AGRO')), \
             patch('app.services.magazyn_dostawy.pallet_split_service.get_db_connection', return_value=mock_conn), \
             patch('app.services.magazyn_dostawy.pallet_split_service.generate_pallet_id', return_value='SUR000000000000000001'):
            ok, msg, result = PalletSplitService.split_pallet(10, 'surowiec', 250, 'test_user')

        assert ok is True
        assert result['id'] == 42
        assert result['nr_palety'] == 'SUR000000000000000001'
        assert result['waga'] == 250
        assert result['mother_new_weight'] == 750
        mock_conn.commit.assert_called_once()

        historia_inserts = [
            sql for sql, _ in executed_sql if 'INSERT INTO palety_historia' in sql
        ]
        assert len(historia_inserts) == 2

        ruch_inserts = [
            sql for sql, _ in executed_sql if 'INSERT INTO' in sql and 'magazyn' in sql and 'ruch' in sql
        ]
        assert len(ruch_inserts) == 2


class TestSplitFinished:
    def test_splits_magazyn_pallet_and_creates_child(self):
        mother = {
            'id': 7,
            'nr_palety': 'AGR777',
            'waga_netto': 500,
            'produkt': 'Mąka 500',
            'lokalizacja': 'MGW02',
            'plan_id': 33,
            'data_planu': datetime(2026, 6, 1),
            'paleta_workowanie_id': 15,
            'nr_plomby': 'PL123',
        }

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.lastrowid = 99

        executed_sql = []

        def capture_execute(sql, params=None):
            executed_sql.append((sql, params))

        mock_cursor.execute.side_effect = capture_execute

        with patch.object(PalletSplitService, 'find_by_id', return_value=(mother, 'AGRO')), \
             patch('app.services.magazyn_dostawy.pallet_split_service.get_db_connection', return_value=mock_conn), \
             patch('app.services.magazyn_dostawy.pallet_split_service.generate_pallet_id', return_value='AGR000000000000000099'):
            ok, msg, result = PalletSplitService.split_pallet(7, 'magazyn', 120, 'lider1')

        assert ok is True
        assert result['id'] == 99
        assert result['waga'] == 120
        assert result['plan_id'] == 33
        assert result['mother_new_weight'] == 380

        historia_inserts = [
            sql for sql, _ in executed_sql if 'INSERT INTO palety_historia' in sql
        ]
        assert len(historia_inserts) == 2

        prod_insert = [
            params for sql, params in executed_sql
            if 'INSERT INTO palety_agro' in sql and params and params[1] == 120
        ]
        assert len(prod_insert) == 1


class TestBuildLabelUrl:
    def test_builds_inventory_label_url(self):
        url = PalletSplitService.build_label_url({
            'source': 'surowiec',
            'nr_palety': 'SUR001',
            'produkt': 'Pszenica',
            'waga': 100,
            'linia': 'AGRO',
        })
        assert '/magazyn-dostawy/podglad-etykiety?' in url
        assert 'nr_palety=SUR001' in url

    def test_builds_finished_label_url(self):
        url = PalletSplitService.build_label_url({
            'source': 'magazyn',
            'id': 55,
            'linia': 'PSD',
        })
        assert url == '/magazyn-dostawy/podglad-etykiety-system/55?linia=PSD'
