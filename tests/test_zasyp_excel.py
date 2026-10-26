from decimal import Decimal
import sqlite3
from unittest.mock import MagicMock, patch
from datetime import date

import pytest
from flask import Blueprint, Flask
from app.services.zasyp_excel_service import ZasypExcelService, ensure_zasyp_excel_schema


@pytest.mark.parametrize('raw,expected', [('15 323,750', '15323.750'), ('0', '0.000'), ('7.125', '7.125')])
def test_parses_explicit_excel_mass(raw, expected):
    assert ZasypExcelService.parse(raw) == Decimal(expected)


@pytest.mark.parametrize('raw', [None, '', '-1', 'NaN', 'Infinity', '1.2345', '100000000000', 'abc'])
def test_rejects_invalid_or_missing_mass(raw):
    with pytest.raises(ValueError):
        ZasypExcelService.parse(raw)


class MemoryCursor:
    def __init__(self, connection):
        self.cursor = connection.cursor()
    def execute(self, sql, values):
        self.cursor.execute(sql.replace('%s', '?'), values)
    def fetchall(self):
        return [dict(row) for row in self.cursor.fetchall()]
    def close(self):
        self.cursor.close()


class MemoryConnection:
    def __init__(self):
        self.raw = sqlite3.connect(':memory:')
        self.raw.row_factory = sqlite3.Row
        self.raw.execute('CREATE TABLE plan_produkcji_agro (id INTEGER, zasyp_id INTEGER, sekcja TEXT, produkt TEXT, data_planu TEXT, is_deleted INTEGER, zasyp_excel_kg NUMERIC)')
    def cursor(self, **kwargs):
        return MemoryCursor(self.raw)
    def add(self, id, source=None, section='Zasyp', product='Milk', day='2026-10-26', deleted=0, kg=None):
        self.raw.execute('INSERT INTO plan_produkcji_agro VALUES (?,?,?,?,?,?,?)', (id,source,section,product,day,deleted,kg))


def test_exact_link_wins_and_legacy_matching_never_guesses_between_batches():
    connection = MemoryConnection()
    connection.add(1, kg=15323.75)
    connection.add(2, kg=900)
    connection.add(10, source=1, section='Workowanie')
    connection.add(11, section='Workowanie')  # Two matching batches: no guessed value.
    connection.add(3, product='Other', kg=0)
    connection.add(12, product='Other', section='Workowanie')  # Legacy unique source, including explicit zero.
    connection.add(4, product='Deleted', deleted=1, kg=123)
    connection.add(13, source=4, product='Deleted', section='Workowanie')
    connection.add(14, source=999, section='Workowanie')
    connection.add(15, product='Missing', section='Workowanie')
    try:
        result = ZasypExcelService.for_work_orders(connection, [10,11,12,13,14,15,10])
        assert result == {10:15323.75,11:None,12:0,13:None,14:None,15:None}
    finally:
        connection.raw.close()


def test_migration_adds_only_nullable_excel_column_and_is_repeatable():
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    ensure_zasyp_excel_schema(cursor)
    sql = cursor.execute.call_args.args[0]
    assert sql == 'ALTER TABLE plan_produkcji_agro ADD COLUMN zasyp_excel_kg DECIMAL(14,3) NULL DEFAULT NULL'
    cursor.reset_mock()
    cursor.fetchone.return_value = ('zasyp_excel_kg',)
    ensure_zasyp_excel_schema(cursor)
    assert cursor.execute.call_count == 1


@pytest.mark.parametrize('amount,status', [('',400), ('-4',400), ('NaN',400), ('15323,75',200), ('0',200)])
def test_closing_batch_validates_before_writes_and_keeps_system_execution_separate(amount,status):
    from app.blueprints.production.orders import register_production_order_routes
    app = Flask(__name__)
    app.secret_key = 'batch-test'
    blueprint = Blueprint('production',__name__)
    register_production_order_routes(blueprint, lambda:'/')
    app.register_blueprint(blueprint)
    client=app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True,login='operator',rola='masteradmin')
    connection=MagicMock()
    cursor=connection.cursor.return_value
    cursor.fetchone.side_effect=[('Milk',date(2026,10,26),'w toku'),(0,),(0,)]
    with patch('app.blueprints.production.orders.get_db_connection',return_value=connection), \
         patch('app.blueprints.production.orders.audit_log') as audit, \
         patch('app.blueprints.production.orders.ZasypEtapyService.stop_any_running_etap'), \
         patch('app.db.create_notifications'), patch('app.db.refresh_bufor_queue'):
        response=client.post('/koniec_zlecenie/1',data={'sekcja':'Zasyp','linia':'AGRO','zasyp_excel_kg':amount,'odrzuty_przesiewacz':'0','final_tonaz':'15000'},headers={'X-Requested-With':'XMLHttpRequest'})
    assert response.status_code == status
    writes=[call.args for call in cursor.execute.call_args_list if call.args[0].lstrip().startswith('UPDATE')]
    if status == 400:
        assert not writes
        connection.commit.assert_not_called()
    else:
        saved=next((sql,values) for sql,values in writes if 'zasyp_excel_kg=%s' in sql)
        assert saved[1] == (15000,0.0,ZasypExcelService.parse(amount),1)
        assert 'zasypy_excel=' in audit.call_args.args[1]
        connection.commit.assert_called_once()


def test_workowanie_header_shows_excel_next_to_execution_without_cleaning_bell_or_register():
    from jinja2 import Environment, ChoiceLoader, DictLoader, FileSystemLoader
    from types import SimpleNamespace
    loader=ChoiceLoader([DictLoader({
        'dashboard/_dashboard_actions_dropdown.html':'',
        'dashboard/_cleaning_notifications.html':'CLEANING_BELL',
        'dashboard/_agro_measurements.html':'',
        'components/_date_picker.html':''
    }),FileSystemLoader('templates')])
    environment=Environment(loader=loader)
    template=environment.get_template('includes/dashboard_top.html')
    plan=[None]*32
    plan[0]=322;plan[2]=15323;plan[3]='w toku';plan[7]=15000
    context=dict(sekcja='Workowanie',linia='AGRO',rola='masteradmin',plan=[plan],
        zasyp_excel_mapa={322:Decimal('15300.125')},zasyp_excel_total=None,
        suma_plan=15323,suma_wykonanie=15000,static_version='test',dzisiaj=date(2026,10,26),
        request=SimpleNamespace(args={'sekcja':'Workowanie','linia':'AGRO'},endpoint='main.index'),
        url_for=lambda endpoint,**kwargs:'/'+endpoint,_=lambda value:value)
    html=template.render(**context)
    assert '15300.125 kg' in html and '15000 kg' in html
    assert html.index('15000 kg') < html.index('15300.125 kg')
    assert 'CLEANING_BELL' not in html and 'Rejestr Przestojów' not in html
    assert 'Zgłoś Przestój' in html
    context['zasyp_excel_mapa']={322:0}
    assert '0 kg' in template.render(**context)
    context['zasyp_excel_mapa']={}
    assert 'brak wpisu' in template.render(**context)
    context['sekcja']='Zasyp'
    assert 'CLEANING_BELL' in template.render(**context)


def test_pdf_workowanie_prints_independent_excel_mass():
    from scripts.reports.pdf_production_sections import PdfProductionSections
    pdf=MagicMock()
    products=['Milk']
    data={'Milk':{'_display':'Milk','Workowanie':(15323,15000,None,None,'Order'), '_zasyp_excel_kg':Decimal('15300.125')}}
    with patch('scripts.reports.pdf_production_sections.rysuj_wiersz_multicell'):
        PdfProductionSections.render_production(pdf,products,data,'2026-10-26',[])
    assert any('15300.125 kg' in str(call) and 'Excel' in str(call) for call in pdf.cell.call_args_list)
