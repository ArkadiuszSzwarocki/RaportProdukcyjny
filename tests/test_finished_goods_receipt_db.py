# cspell:words sscc pytestmark lastrowid potwierdzil
import uuid
from unittest.mock import MagicMock

import pytest
from flask import session
from app.db import get_db_connection, get_table_name
from app.services.magazyn_dostawy.acceptance_service import AcceptanceService
from app.services.warehouse_pallet_service import WarehousePalletService

pytestmark = pytest.mark.require_db


@pytest.fixture
def pending_production(app):
    code = 'AGR-TEST-RECEIPT-' + uuid.uuid4().hex.upper()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SHOW COLUMNS FROM palety_agro LIKE 'potwierdzil_login'")
    if not cursor.fetchone():
        cursor.execute('ALTER TABLE palety_agro ADD COLUMN potwierdzil_login VARCHAR(100) NULL')
    cursor.execute("INSERT INTO plan_produkcji_agro(data_planu,sekcja,produkt,tonaz,status) VALUES(CURRENT_DATE,'Workowanie','Test finished',100,'w toku')")
    plan_id = cursor.lastrowid
    cursor.execute("INSERT INTO palety_agro(plan_id,nr_palety,waga,tara,status,data_dodania) VALUES(%s,%s,100,25,'do_przyjecia',NOW())",(plan_id,code))
    production_id = cursor.lastrowid
    conn.commit()
    conn.close()
    yield production_id,code
    conn = get_db_connection()
    cursor = conn.cursor()
    for table in ('magazyn_palety_agro','magazyn_palety'):
        cursor.execute(f'DELETE FROM {table} WHERE nr_palety=%s',(code,))
    cursor.execute('DELETE FROM palety_historia WHERE nr_palety=%s',(code,))
    cursor.execute('DELETE FROM palety_agro WHERE id=%s',(production_id,))
    cursor.execute('DELETE FROM plan_produkcji_agro WHERE id=%s',(plan_id,))
    conn.commit()
    conn.close()


def state(code):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT status FROM palety_agro WHERE nr_palety=%s',(code,))
    status = cursor.fetchone()[0]
    table = get_table_name('magazyn_palety','AGRO')
    cursor.execute(f'SELECT waga_netto,lokalizacja FROM {table} WHERE nr_palety=%s',(code,))
    stock = cursor.fetchall()
    cursor.execute("SELECT nr_palety,lokalizacja_docelowa FROM palety_historia WHERE nr_palety=%s AND akcja='PRZYJECIE_WG'",(code,))
    history = cursor.fetchall()
    conn.close()
    return status,stock,history


@pytest.mark.parametrize('entry',['scanner','workowanie'])
def test_both_entry_points_write_same_agro_stock_and_sscc_history(app,pending_production,entry):
    production_id,code = pending_production
    if entry == 'scanner':
        result = AcceptanceService.accept_production_pallet(code,'MGW01','AGRO','pytest',100)
        assert result[0], result[1]
    else:
        with app.test_request_context(method='POST',data={'waga_palety':'100','lokalizacja':'MGW01'}):
            session['rola']='magazynier'
            result = WarehousePalletService.potwierdz_palete(production_id,'AGRO','pytest',app,None,None,True,'/')
        assert result[1] == 200, result
    status,stock,history = state(code)
    assert status in ('przyjeta','w_magazynie')
    assert stock == [(100,'MGW01')]
    assert history == [(code,'MGW01')]


@pytest.mark.parametrize('entry',['scanner','workowanie'])
def test_history_failure_rolls_back_status_and_stock(app,pending_production,monkeypatch,entry):
    production_id,code = pending_production
    from app.services.pallets.finished_goods_receipt import FinishedGoodsReceipt
    original = FinishedGoodsReceipt.write
    def failing_receipt(connection,**arguments):
        proxy = MagicMock(wraps=connection)
        cursor = connection.cursor(dictionary=True)
        wrapper = MagicMock(wraps=cursor)
        def execute(sql,params=None):
            if 'INSERT INTO palety_historia' in sql:
                raise RuntimeError('History failure')
            return cursor.execute(sql,params)
        wrapper.execute.side_effect=execute
        proxy.cursor.return_value=wrapper
        return original(proxy,**arguments)
    monkeypatch.setattr(FinishedGoodsReceipt,'write',failing_receipt)
    if entry == 'scanner':
        assert not AcceptanceService.accept_production_pallet(code,'MGW01','AGRO','pytest',100)[0]
    else:
        with app.test_request_context(method='POST',data={'waga_palety':'100','lokalizacja':'MGW01'}):
            session['rola']='magazynier'
            result = WarehousePalletService.potwierdz_palete(production_id,'AGRO','pytest',app,None,None,True,'/')
        assert result[1] == 400
    assert state(code) == ('do_przyjecia',[],[])


def test_second_receipt_does_not_duplicate_stock_or_history(pending_production):
    _,code = pending_production
    assert AcceptanceService.accept_production_pallet(code,'MGW01','AGRO','pytest',100)[0]
    before = state(code)
    assert not AcceptanceService.accept_production_pallet(code,'MGW01','AGRO','pytest',100)[0]
    assert state(code) == before


@pytest.mark.parametrize('quantity',[float('nan'),float('inf'),-1])
def test_invalid_weight_never_marks_production_as_received(pending_production,quantity):
    _,code = pending_production
    assert not AcceptanceService.accept_production_pallet(code,'MGW01','AGRO','pytest',quantity)[0]
    assert state(code) == ('do_przyjecia',[],[])
