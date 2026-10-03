"""Reject invalid quantities and duplicate components before stock writes."""
from unittest.mock import MagicMock

import pytest

from app.services.magazyn_dostawy.pallet_mix_service import PalletMixService
from app.services.magazyn_dostawy.pallet_split_service import PalletSplitService
from app.services.warehouse_v2.pallet_relocation_service import PalletRelocationService
from app.services.warehouse_v2_service import WarehouseV2Service


@pytest.mark.parametrize('quantity', [float('nan'), float('inf'), -1, 0, 'NaN', 'invalid'])
@pytest.mark.parametrize('service', [PalletRelocationService, WarehouseV2Service])
def test_invalid_move_quantity_never_opens_database(monkeypatch, quantity, service):
    connect = MagicMock()
    path = ('app.services.warehouse_v2.pallet_relocation_service' if service is PalletRelocationService
            else 'app.services.warehouse_v2_service')
    monkeypatch.setattr(path + '.get_db_connection', connect)
    assert not service.move_pallet(1, 'Surowiec', 'MS01', 'user', amount_to_move=quantity)[0]
    connect.assert_not_called()


@pytest.mark.parametrize('quantity', [float('nan'), float('inf'), 'NaN', 'invalid'])
def test_invalid_split_quantity_cannot_lookup_stock(monkeypatch, quantity):
    lookup = MagicMock()
    monkeypatch.setattr(PalletSplitService, 'find_by_sscc', lookup)
    assert not PalletSplitService.split_pallet(mother_sscc='P1', weight_to_take=quantity)[0]
    lookup.assert_not_called()


def test_same_physical_pallet_cannot_create_double_weight_mix(monkeypatch):
    conn = MagicMock()
    pal = {'id': 12, 'nr_palety': 'P1', 'source': 'surowiec', 'linia': 'AGRO',
           'waga': 500, 'stan_magazynowy': 500, 'lokalizacja': 'MS01'}
    monkeypatch.setattr('app.services.magazyn_dostawy.pallet_mix_service.get_db_connection', lambda: conn)
    monkeypatch.setattr(PalletSplitService, 'find_by_sscc', lambda code: pal)
    ok, message, _ = PalletMixService.mix_pallets([
        {'nr_palety': 'P1', 'weight_to_take': 100},
        {'nr_palety': 'p1', 'weight_to_take': 100},
    ], 'Test mix')
    assert not ok
    assert 'dwa razy' in message
    conn.commit.assert_not_called()
    conn.cursor.return_value.execute.assert_not_called()
