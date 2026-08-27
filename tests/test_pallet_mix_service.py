"""Testy dla PalletMixService - wklejanie, miksowanie surowców i wyrobów gotowych."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.services.magazyn_dostawy.pallet_mix_service import PalletMixService, generate_mix_pallet_id


class TestGenerateMixPalletId:
    def test_generates_valid_mix_id(self):
        mix_id = generate_mix_pallet_id()
        assert mix_id.startswith('MIX')
        assert len(mix_id) == 18


class TestPalletMixValidation:
    def test_rejects_empty_components(self):
        ok, msg, result = PalletMixService.mix_pallets([], 'MIX Test')
        assert ok is False
        assert 'Brak składników' in msg
        assert result is None

    def test_allows_mixing_surowiec_pallets(self):
        mother_sur = {
            'id': 10,
            'nr_palety': 'SUR20260825001',
            'nazwa': 'Mąka Pszenna',
            'stan_magazynowy': 500,
            'waga': 500,
            'lokalizacja': 'MGW01',
            'data_produkcji': datetime(2026, 1, 1),
            'termin_przydatnosci': datetime(2027, 1, 1),
            'nr_partii': 'PARTIA1',
            'source': 'surowiec',
            'linia': 'AGRO'
        }

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.lastrowid = 101

        components = [
            {
                'mother_id': 10,
                'nr_palety': 'SUR20260825001',
                'weight_to_take': 100
            }
        ]

        with patch('app.services.magazyn_dostawy.pallet_split_service.PalletSplitService.find_by_sscc', return_value=mother_sur), \
             patch('app.services.magazyn_dostawy.pallet_mix_service.get_db_connection', return_value=mock_conn):
            
            ok, msg, result = PalletMixService.mix_pallets(components, 'MIX Mąka Specjalna', user_login='operator', linia='AGRO')

        assert ok is True
        assert 'pomyślnie' in msg
        assert result['mix_pallet']['produkt'] == 'MIX Mąka Specjalna'
        assert result['mix_pallet']['waga'] == 100
        assert result['sources'][0]['waga_odjeta'] == 100
        assert result['sources'][0]['weight_taken'] == 100

    def test_allows_taking_entire_pallet_weight(self):
        mother_sur = {
            'id': 12,
            'nr_palety': 'SUR20260825050',
            'nazwa': 'Mąka Jęczmienna',
            'stan_magazynowy': 50,
            'waga': 50,
            'lokalizacja': 'MGW01',
            'source': 'surowiec',
            'linia': 'AGRO'
        }

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.lastrowid = 102

        components = [
            {
                'mother_id': 12,
                'nr_palety': 'SUR20260825050',
                'weight_to_take': 50
            }
        ]

        with patch('app.services.magazyn_dostawy.pallet_split_service.PalletSplitService.find_by_sscc', return_value=mother_sur), \
             patch('app.services.magazyn_dostawy.pallet_mix_service.get_db_connection', return_value=mock_conn):
            
            ok, msg, result = PalletMixService.mix_pallets(components, 'MIX Pełny 50kg', user_login='operator', linia='AGRO')

        assert ok is True
        assert result['mix_pallet']['waga'] == 50
        assert result['sources'][0]['mother_new_weight'] == 0.0
