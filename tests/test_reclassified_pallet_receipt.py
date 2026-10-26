from unittest.mock import MagicMock,patch
import sqlite3
import pytest
from flask import Flask,session
from app.services.warehouse_pallet_service import WarehousePalletService
from app.services.magazyn_dostawy.acceptance_service import AcceptanceService
from app.utils.queries_split.warehouse import WarehouseQueries


@pytest.mark.parametrize('status',['przeklasyfikowana','zuzyta','zarchiwizowana','zamknieta'])
def test_old_warehouse_confirmation_cannot_recreate_finalized_stock_even_when_forced(status):
    app=Flask(__name__);app.secret_key='receipt-test'
    connection=MagicMock();cursor=connection.cursor.return_value
    cursor.fetchone.return_value=(316,status,660,'SUR000001790591646672',None)
    with app.test_request_context(method='POST',data={'waga_palety':'999','force_accept':'1','check_only':'1'}), \
         patch('app.services.warehouse_pallet_service.get_db_connection',return_value=connection):
        session['rola']='masteradmin'
        result,code,_=WarehousePalletService.potwierdz_palete(933,'AGRO','operator',app,None,None,True,'/')
    assert code==409 and result['success'] is False
    assert all(call.args[0].lstrip().startswith('SELECT') for call in cursor.execute.call_args_list)
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    connection.close.assert_called_once()


def test_scanner_receipt_fallback_rejects_an_already_reclassified_pallet():
    connection=MagicMock();cursor=connection.cursor.return_value
    def fetch():
        sql=cursor.execute.call_args.args[0]
        if "p.status = 'do_przyjecia'" in sql:return None
        return {'id':933,'status':'przeklasyfikowana','nr_palety':'SUR000001790591646672','waga':660}
    cursor.fetchone.side_effect=fetch
    with patch('app.services.magazyn_dostawy.acceptance_service.get_db_connection',return_value=connection), \
         patch('app.services.pallets.finished_goods_receipt.FinishedGoodsReceipt.write') as stock:
        result=AcceptanceService.accept_production_pallet('SUR000001790591646672','MGW01',linia='AGRO',confirmed_weight=660)
    assert result[0] is False
    assert 'przeklasyfikowana' in result[1]
    stock.assert_not_called()
    assert all(call.args[0].lstrip().startswith('SELECT') for call in cursor.execute.call_args_list)
    connection.commit.assert_not_called()


def test_pending_list_excludes_finalized_history_but_keeps_real_pending_pallets():
    connection=sqlite3.connect(':memory:')
    connection.execute('CREATE TABLE palety_agro(id INTEGER,plan_id INTEGER,waga REAL,status TEXT,nr_palety TEXT,data_dodania TEXT)')
    connection.execute('CREATE TABLE plan_produkcji_agro(id INTEGER,sekcja TEXT,produkt TEXT)')
    connection.execute("INSERT INTO plan_produkcji_agro VALUES (1,'Workowanie','Test')")
    statuses=['przeklasyfikowana','do_przyjecia','zuzyta',None,'przyjeta','w_magazynie','zamknieta']
    for id,status in enumerate(statuses,1):
        connection.execute('INSERT INTO palety_agro VALUES (?,1,660,?,?,?)',(id,status,'SSCC'+str(id),'2026-10-26'))
    class Cursor:
        def execute(self,sql,params):self.result=connection.execute(sql.replace('%s','?'),params)
        def fetchall(self):return self.result.fetchall()
    before=connection.total_changes
    result=WarehouseQueries.get_unconfirmed_paletki('2026-10-26',linia='AGRO',cursor=Cursor())
    assert {row[0] for row in result}=={2,4}
    assert connection.total_changes==before
    connection.close()
