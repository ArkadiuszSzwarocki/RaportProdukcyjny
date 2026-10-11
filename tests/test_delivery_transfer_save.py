from unittest.mock import MagicMock
import pytest
from app.services.magazyn_dostawy.commands.internal_transfer_processor import InternalTransferProcessor


def test_find_active_pallet_by_sscc_queries_magazyn_palety_with_produkt_not_nazwa():
    cursor = MagicMock()
    cursor.fetchone.return_value = None

    # Call _find_active_pallet_by_sscc with a test SSCC
    res, p_type, tbl = InternalTransferProcessor._find_active_pallet_by_sscc(cursor, "51810000017109100589", "PSD")
    assert res is None

    # Verify that cursor.execute was called and none of the SQL statements query COALESCE(produkt, nazwa)
    executed_sqls = [call_args[0][0] for call_args in cursor.execute.call_args_list]
    for sql in executed_sqls:
        assert "COALESCE(produkt, nazwa)" not in sql, f"Query should not use COALESCE(produkt, nazwa): {sql}"
        if "magazyn_palety" in sql:
            assert ", nazwa FROM" not in sql and ", nazwa," not in sql
            assert "produkt AS nazwa" in sql
