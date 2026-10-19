from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.services.warehouse_history.history_enricher_service import HistoryEnricherService
from app.services.warehouse_history.history_query_service import HistoryQueryService
from app.services.warehouse_history.station_filter import matches_station, station_search_pattern


@pytest.mark.parametrize('location,expected', [
    ('BB14', True), ('bb14', True), ('MS01 -> BB14', True), ('BB14 -> MS01', True),
    ('BB140', False), ('BB141', False), ('XBB14', False), ('BB1', False), ('BB15', False),
])
def test_station_code_matches_complete_location_or_route_endpoint(location, expected):
    assert matches_station({'stacja': location}, station_search_pattern(' bb14 ')) == expected


def row(number, src, dst, typ='PRZESUNIECIE', comment=''):
    return {
        'id': number, 'paleta_id': number, 'nr_palety': f'SUR{number:018}',
        'created_at': datetime(2026, 10, 19, 8) + timedelta(minutes=number),
        'lokalizacja_zrodlowa': src, 'lokalizacja_docelowa': dst,
        'typ_ruchu': typ, 'linia_ruch': 'AGRO', 'typ_palety': 'surowiec',
        'surowiec_nazwa': 'Surowiec testowy', 'waga_ref': number, 'komentarz': comment,
    }


def enrich(rows, station, limit=100, operation=None):
    with patch('app.services.warehouse_history.history_enricher_service.HistoryIndexer.get_table_columns', return_value=set()), \
         patch('app.services.warehouse_history.history_enricher_service.PalletDetailsEnricher.enrich_unresolved_pallets'), \
         patch('app.services.warehouse_history.history_enricher_service.OrderDetailsEnricher.attach_production_orders'):
        return HistoryEnricherService.enrich_and_filter_history(
            MagicMock(), rows, 'AGRO', None, station, operation, limit,
        )


def test_station_filter_excludes_unrelated_creations_before_result_limit():
    rows = [row(1, 'MS01', 'BB14'), row(2, 'BB14', 'MS01'), row(3, 'MS01', 'BB140')]
    rows += [row(i, 'Linia AGRO', 'OCZEKUJĄCE', 'UTWORZENIE') for i in range(4, 20)]
    result = enrich(rows, ' bb14 ', limit=2)
    assert [item['id'] for item in result] == [2, 1]


def test_legacy_station_record_can_use_exact_station_from_comment():
    result = enrich([row(1, None, None, 'WYDANIE_PRODUKCJA', 'Wydano do stacji BB14'),
                     row(2, None, None, 'WYDANIE_PRODUKCJA', 'Wydano do stacji BB140')], 'bb14')
    assert [item['id'] for item in result] == [1]


def test_empty_station_preserves_complete_history_and_operation_filter():
    result = enrich([row(1, 'MS01', 'BB14'), row(2, 'MS01', 'BB15'),
                     row(3, 'Linia AGRO', 'OCZEKUJĄCE', 'UTWORZENIE')], '')
    assert {item['id'] for item in result} == {1, 2, 3}
    filtered = enrich([row(1, 'MS01', 'BB14'), row(2, 'BB14', 'BB14', 'DOSYPKA')], 'BB14', operation='DOSYPKA')
    assert [item['id'] for item in filtered] == [2]


def test_sql_filters_all_station_sources_with_bound_complete_code_pattern():
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    with patch('app.services.warehouse_history.history_query_service.HistoryIndexer.get_table_columns',
               return_value={'nr_palety'}):
        HistoryQueryService.query_all_history_sources(
            cursor, MagicMock(), 'ALL', None, None, None, ' bb14 ', None, 100,
        )
    filtered_queries = [call for call in cursor.execute.call_args_list
                        if any(table in call.args[0] for table in
                               ('FROM palety_historia ph', 'FROM magazyn_ruch r', 'FROM magazyn_agro_ruch r',
                                'FROM magazyn_palety mp', 'FROM magazyn_palety_agro mpa'))]
    assert len(filtered_queries) == 5
    for call in filtered_queries:
        assert ' REGEXP %s' in call.args[0]
        assert station_search_pattern('BB14') in call.args[1]
        assert '% bb14 %' not in call.args[1]
