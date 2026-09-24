import pytest
from unittest.mock import MagicMock, patch
from app.services.magazyn_dostawy.commands.pallet_lock_manager import PalletLockManager
from app.services.agro_workowanie_bigbag_service import AgroWorkowanieBigBagService


def test_reconcile_orphan_transfer_locks_commits_with_cursor():
    """Verify that when cursor is passed, conn is extracted and conn.commit() is invoked."""
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_cursor._connection = mock_conn

    # 1. No active orders with in-flight items
    # 2. No manually blocked history items
    # 3. For each table, return one blocked item
    mock_cursor.fetchall.side_effect = [
        [],  # active orders
        [],  # manual blocked history
        [{'id': 999, 'nr_palety': 'PSD000001790079009978'}],  # magazyn_surowce
        [],  # magazyn_opakowania
        [],  # magazyn_palety
        [],  # magazyn_palety_agro
        [],  # magazyn_dodatki
        [],  # palety_workowanie
        [],  # palety_agro
    ]

    unblocked = PalletLockManager.reconcile_orphan_transfer_locks(mock_cursor)

    assert unblocked == 1
    mock_cursor.execute.assert_any_call("UPDATE magazyn_surowce SET is_blocked = 0 WHERE id = %s", (999,))
    assert mock_conn.commit.called


def test_agro_workowanie_bigbag_auto_reconcile_orphan_lock():
    """Verify that AgroWorkowanieBigBagService auto-reconciles orphan locks during lookup."""
    with patch.object(PalletLockManager, 'reconcile_orphan_transfer_locks', return_value=1) as mock_reconcile:
        with patch.object(AgroWorkowanieBigBagService, 'lookup_bigbag') as mock_lookup:
            mock_pallet_blocked = {
                'id': 2229,
                'nr_palety': 'PSD000001790079009978',
                'nazwa': 'MLECZNA PYCHA',
                'waga': 759.0,
                'lokalizacja': 'MP01',
                'nr_partii': 'BRAK',
                'data_produkcji': '2026-09-22',
                'data_przydatnosci': '',
                'is_blocked': True,
                'typ_palety': 'Wyrób Gotowy',
                'linia': 'AGRO',
                'table_name': 'magazyn_palety',
                'qty_column': 'waga_netto'
            }
            mock_pallet_unblocked = dict(mock_pallet_blocked)
            mock_pallet_unblocked['is_blocked'] = False

            # First call returns blocked, after reconcile returns unblocked
            mock_lookup.side_effect = [mock_pallet_blocked, mock_pallet_unblocked]

            # In add_bigbag_to_plan:
            with patch('app.services.agro_workowanie_bigbag_service.get_db_connection') as mock_get_conn:
                mock_conn = MagicMock()
                mock_cur = MagicMock()
                mock_get_conn.return_value = mock_conn
                mock_conn.cursor.return_value = mock_cur
                mock_cur.fetchone.return_value = {'id': 100, 'produkt': 'Test', 'nazwa_zlecenia': 'Test'}

                ok, msg, settlement = AgroWorkowanieBigBagService.add_bigbag_to_plan(
                    plan_id=100,
                    code='PSD000001790079009978',
                    worker_login='operator',
                    linia='AGRO'
                )

                assert mock_reconcile.called
                assert ok is True
