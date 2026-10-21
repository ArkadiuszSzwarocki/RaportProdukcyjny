from unittest.mock import MagicMock, patch

from app.services.scanner.scanner_lookup_service import ScannerLookupService
from app.services.scanner.scanner_suggestions_service import find_pallet_suggestions


def test_inventory_lookup_does_not_assign_a_production_owner_to_raw_stock():
    cursor = MagicMock()
    cursor.fetchone.return_value = {'id': 3387, 'linia': None}
    row = ScannerLookupService.lookup_inventory_row(cursor, 'magazyn_surowce', 'AGRO',
                                                  qty_col='stan_magazynowy', pallet_no='SUR123456')
    assert row['linia'] is None
    sql = cursor.execute.call_args.args[0]
    assert "NULL AS linia" in sql


def test_suffix_search_returns_all_matches_and_queries_shared_tables_once():
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchall.side_effect = [
        [{'id': 1, 'nr_palety': 'SUR000001123456', 'linia': 'PSD', 'ilosc': 10},
         {'id': 2, 'nr_palety': 'SUR000002123456', 'linia': 'AGRO', 'ilosc': 20}], [], [], [],
    ]
    with patch('app.services.scanner.scanner_suggestions_service.get_db_connection', return_value=connection), patch(
        'app.services.scanner.scanner_suggestions_service.get_table_name', side_effect=lambda base, line: base
    ):
        rows = find_pallet_suggestions('123456')
    assert len(rows) == 2
    assert cursor.execute.call_count == 4
    for call in cursor.execute.call_args_list:
        sql, params = call.args
        assert params[-1] == '%123456'
        assert '>0' in sql
        assert 'LIMIT 30' in sql
    connection.close.assert_called_once()


def test_suggestions_validate_length_and_filter_actual_hall(client):
    with client.session_transaction() as session:
        session.update(zalogowany=True, login='pytest', rola='masteradmin', grupa='ALL')
    with patch('app.services.scanner.scanner_suggestions_service.find_pallet_suggestions') as find, patch(
        'app.core.scanner_permissions.scanner_resource_read_allowed', side_effect=lambda row: row['linia'] == 'PSD'
    ):
        assert client.get('/agro/scanner/pallet-suggestions?digits=12345').status_code == 400
        find.assert_not_called()
        find.return_value = [{'linia': 'PSD', 'nr_palety': 'SUR123456'}, {'linia': 'AGRO', 'nr_palety': 'SUR223456'}]
        result = client.get('/agro/scanner/pallet-suggestions?digits=123456&linia=AGRO')
    assert result.status_code == 200
    assert result.get_json()['pallets'] == [{'linia': 'PSD', 'nr_palety': 'SUR123456'}]
