import json
from unittest.mock import MagicMock,patch
from app.core.contexts import _fetch_delivery_counters
from app.services.magazyn_dostawy.delivery_queries import DeliveryQueries


def test_central_and_osip_movement_counters_are_separate():
    connection=MagicMock()
    connection.cursor.return_value.fetchall.return_value=[
        ('ALL',json.dumps([{'accepted':False}]),'MS01'),
        ('OSIP',json.dumps([{'accepted':False},{'accepted':False}]),'R01'),
    ]
    with patch('app.db.get_db_connection',return_value=connection):result=_fetch_delivery_counters()
    assert result['pending_transfer_orders']['CENTRALA']==1
    assert result['pending_transfer_orders']['OSIP']==1
    assert result['pending_transfer_pallets']['CENTRALA']==1
    assert result['pending_transfer_pallets']['OSIP']==2
    assert result['open_transfer_orders']['CENTRALA']==1


def test_central_movement_list_excludes_osip_at_query_boundary():
    connection=MagicMock();connection.cursor.return_value.fetchall.return_value=[]
    with patch('app.services.magazyn_dostawy.delivery_queries.get_db_connection',return_value=connection):
        DeliveryQueries.get_dostawy('ALL',warehouse_scope='centrala')
    sql=connection.cursor.return_value.execute.call_args.args[0]
    assert "!= 'OSIP'" in sql


def test_osip_movement_list_stays_in_osip():
    connection=MagicMock();connection.cursor.return_value.fetchall.return_value=[]
    with patch('app.services.magazyn_dostawy.delivery_queries.get_db_connection',return_value=connection):
        DeliveryQueries.get_dostawy('OSIP',warehouse_scope='osip')
    assert connection.cursor.return_value.execute.call_args.args[1]==('OSIP',)
