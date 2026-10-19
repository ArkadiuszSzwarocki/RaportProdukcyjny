from unittest.mock import MagicMock, patch

import pytest
from mysql.connector.errors import ProgrammingError

from app.services.osip_transfer_service import OsipTransferService


@pytest.mark.parametrize('source,location', [('MS01', 'MS01'), ('OSIP', 'A01')])
def test_lookup_works_without_optional_legacy_agro_stock_tables(source, location):
    connection = MagicMock()
    cursor = connection.cursor.return_value

    def execute(sql, params):
        if any('FROM ' + table + ' ' in sql for table in ('magazyn_agro_surowce', 'magazyn_agro_opakowania', 'magazyn_palety_agro')):
            raise ProgrammingError('Optional table absent', errno=1146)
        cursor.fetchall.return_value = ([dict(id=7, nr_palety='SUR-123', product_name='Test', quantity=100, lokalizacja=location)]
                                       if 'FROM magazyn_surowce ' in sql else [])

    cursor.execute.side_effect = execute
    with patch('app.services.osip_transfer_service.get_db_connection', return_value=connection):
        pallet = OsipTransferService.lookup_transfer_pallet('SUR-123', source)
    assert pallet['pallet_id'] == 7
    assert pallet['requested_qty'] == 100
    assert pallet['item_type'] == 'raw'
    connection.close.assert_called_once()


@pytest.mark.parametrize('table,code', [('magazyn_surowce', 1146), ('magazyn_agro_surowce', 1142)])
def test_lookup_does_not_hide_missing_core_tables_or_denied_access(table, code):
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchall.return_value = []

    def execute(sql, params):
        if 'FROM ' + table + ' ' in sql:
            raise ProgrammingError('Stock read unavailable', errno=code)

    cursor.execute.side_effect = execute
    with patch('app.services.osip_transfer_service.get_db_connection', return_value=connection):
        with pytest.raises(ProgrammingError):
            OsipTransferService.lookup_transfer_pallet('SUR-123', 'OSIP')
    connection.close.assert_called_once()
