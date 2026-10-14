# cspell:words sscc pytestmark lastrowid potwierdzil
import uuid
from unittest.mock import MagicMock

import pytest
from flask import session
from app.db import get_db_connection, get_table_name
from app.services.magazyn_dostawy.acceptance_service import AcceptanceService
from app.services.warehouse_pallet_service import WarehousePalletService

pytestmark = pytest.mark.require_db


@pytest.fixture(params=['AGRO', 'PSD'])
def pending_production(app, request):
    line = request.param
    code = line + '-TEST-RECEIPT-' + uuid.uuid4().hex.upper()
    production_table = get_table_name('palety_workowanie', line)
    plan_table = get_table_name('plan_produkcji', line)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"SHOW COLUMNS FROM {production_table} LIKE 'potwierdzil_login'")
    if not cursor.fetchone():
        cursor.execute(f'ALTER TABLE {production_table} ADD COLUMN potwierdzil_login VARCHAR(100) NULL')
    cursor.execute(f"INSERT INTO {plan_table}(data_planu,sekcja,produkt,tonaz,status) VALUES(CURRENT_DATE,'Workowanie','Test finished',100,'w toku')")
    plan_id = cursor.lastrowid
    cursor.execute(f"INSERT INTO {production_table}(plan_id,nr_palety,waga,tara,status,data_dodania) VALUES(%s,%s,100,25,'do_przyjecia',NOW())",(plan_id,code))
    production_id = cursor.lastrowid
    conn.commit()
    conn.close()
    yield production_id,code,line
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM magazyn_palety WHERE nr_palety=%s',(code,))
    cursor.execute('DELETE FROM palety_historia WHERE nr_palety=%s',(code,))
    cursor.execute(f'DELETE FROM {production_table} WHERE id=%s',(production_id,))
    cursor.execute(f'DELETE FROM {plan_table} WHERE id=%s',(plan_id,))
    conn.commit()
    conn.close()


def state(code):
    line = code.split('-')[0]
    production_table = get_table_name('palety_workowanie', line)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f'SELECT status FROM {production_table} WHERE nr_palety=%s',(code,))
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
    production_id,code,line = pending_production
    if entry == 'scanner':
        result = AcceptanceService.accept_production_pallet(code,'MGW01',line,'pytest',100)
        assert result[0], result[1]
    else:
        with app.test_request_context(method='POST',data={'waga_palety':'100','lokalizacja':'MGW01'}):
            session['rola']='magazynier'
            result = WarehousePalletService.potwierdz_palete(production_id,line,'pytest',app,None,None,True,'/')
        assert result[1] == 200, result
    status,stock,history = state(code)
    assert status in ('przyjeta','w_magazynie')
    assert stock == [(100,'MGW01')]
    assert history == [(code,'MGW01')]


@pytest.mark.parametrize('entry',['scanner','workowanie'])
def test_history_failure_rolls_back_status_and_stock(app,pending_production,monkeypatch,entry):
    production_id,code,line = pending_production
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
        assert not AcceptanceService.accept_production_pallet(code,'MGW01',line,'pytest',100)[0]
    else:
        with app.test_request_context(method='POST',data={'waga_palety':'100','lokalizacja':'MGW01'}):
            session['rola']='magazynier'
            result = WarehousePalletService.potwierdz_palete(production_id,line,'pytest',app,None,None,True,'/')
        assert result[1] == 400
    assert state(code) == ('do_przyjecia',[],[])


def test_second_receipt_does_not_duplicate_stock_or_history(pending_production):
    _,code,line = pending_production
    assert AcceptanceService.accept_production_pallet(code,'MGW01',line,'pytest',100)[0]
    before = state(code)
    assert not AcceptanceService.accept_production_pallet(code,'MGW01',line,'pytest',100)[0]
    assert state(code) == before


@pytest.mark.parametrize('quantity',[float('nan'),float('inf'),-1])
def test_invalid_weight_never_marks_production_as_received(pending_production,quantity):
    _,code,line = pending_production
    assert not AcceptanceService.accept_production_pallet(code,'MGW01',line,'pytest',quantity)[0]
    assert state(code) == ('do_przyjecia',[],[])
