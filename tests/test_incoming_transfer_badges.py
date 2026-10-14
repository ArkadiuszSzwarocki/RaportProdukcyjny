"""Incoming transfer badges belong to the receiving warehouse."""
from unittest.mock import MagicMock,patch

from app.core.contexts import _fetch_osip_transfers_count


def test_counts_are_split_by_destination():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [
        dict(id=1,destination_warehouse='MS01',unreceived_count=23),
        dict(id=2,destination_warehouse='OSIP',unreceived_count=5),
        dict(id=3,destination_warehouse='OSIP',unreceived_count=2)]
    with patch('app.core.database.get_db_connection',return_value=conn):
        result = _fetch_osip_transfers_count()
    assert result['incoming_transfer_counts'] == {
        'centrala':dict(documents=1,pallets=23),'osip':dict(documents=2,pallets=7)}
