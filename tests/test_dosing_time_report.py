# cspell:words Naważanie SPECJAL wydozowan executescript
"""Batch timing reports preserve process sequence and distinguish pauses from work."""
from datetime import date,datetime
from unittest.mock import MagicMock,patch
import pytest
from flask import Flask
from jinja2 import ChoiceLoader,DictLoader
from app.services.dosing_time_report_service import DosingTimeReportService


def order(line='AGRO',id=1):return dict(id=id,linia=line,produkt='MILK SPECJAL',data_planu=date(2026,10,27),status='w toku')
def stage(id,code,start='2026-10-27 08:00:00',stop='2026-10-27 08:10:00',line='AGRO',**extra):return dict(id=id,plan_id=1,linia=line,szarza_nr=1,etap=code,czas_start=start,czas_stop=stop,**extra)


def test_repeated_stages_follow_process_sequence_not_numeric_code():
    rows=[stage(i,code) for i,code in enumerate([5,41,31,4,3,2,1],1)]
    report=DosingTimeReportService.build([order()],rows,now=datetime(2026,10,27,10))
    entries=report['orders'][0]['batches'][0]['stages']
    assert [entry['code'] for entry in entries]==['1','2','3','4','3.2','4.2','5']
    assert [entry['sequence'] for entry in entries]==list(range(1,8))
    assert entries[4]['name']=='Dosypka — cykl 2'
    assert entries[0]['actual_sequence']==7


def test_running_pause_is_subtracted_once_and_live_is_explicit():
    row=stage(1,1,stop=None,is_paused=1,pauza_start='2026-10-27 08:15:00',pauza_sekundy=60)
    report=DosingTimeReportService.build([order()],[row],now=datetime(2026,10,27,8,20))
    result=report['orders'][0]['batches'][0]['stages'][0]
    assert result['gross_s']==1200 and result['pause_s']==360 and result['work_s']==840
    assert result['state']=='W pauzie' and result['live']
    assert result['work']=='00:14:00'


def test_missing_or_invalid_times_are_not_zero_duration_measurements():
    rows=[stage(1,1,start=None),stage(2,2,start='2026-10-27 09:00:00',stop='2026-10-27 08:00:00')]
    report=DosingTimeReportService.build([order()],rows,now=datetime(2026,10,27,10))
    assert report['kpis']['missing']==2
    assert all(row['work']=='—' for row in report['orders'][0]['batches'][0]['stages'])
    assert report['stage_chart']==[]


def test_same_ids_on_different_halls_do_not_mix_and_selection_is_exact():
    report=DosingTimeReportService.build([order(),order('PSD')],[stage(1,1),stage(2,1,line='PSD')],selected='PSD:1')
    assert len(report['options'])==2 and len(report['orders'])==1
    assert report['orders'][0]['line']=='PSD'
    assert report['orders'][0]['batches'][0]['stages'][0]['id']==2


def test_elapsed_time_is_different_from_sum_of_overlapping_stages():
    rows=[stage(1,1),stage(2,2)]
    result=DosingTimeReportService.build([order()],rows)['orders'][0]['batches'][0]
    assert result['gross']=='00:20:00' and result['elapsed']=='00:10:00'


def test_loader_only_reads_and_supports_schema_without_pause_fields():
    conn=MagicMock();cursor=conn.cursor.return_value
    def result():
        sql=cursor.execute.call_args.args[0]
        if sql.startswith('SHOW'):return [dict(Field='id')]
        if sql.startswith('SELECT p.id'):
            row=order();row.pop('linia');return [row]
        if sql.startswith('SELECT e.id'):
            row=stage(1,1);row.pop('linia');return [row]
        return []
    cursor.fetchall.side_effect=result
    with patch('app.services.dosing_time_report_service.get_db_connection',return_value=conn):
        report=DosingTimeReportService.load(date(2026,10,1),date(2026,10,27),'AGRO')
    assert report['kpis']['closed']==1
    assert all(call.args[0].startswith(('SHOW','SELECT')) for call in cursor.execute.call_args_list)
    conn.commit.assert_not_called();conn.close.assert_called_once()


def app():
    from app.blueprints.zarzad.base import zarzad_bp
    instance=Flask(__name__,template_folder='../templates',static_folder='../static');instance.secret_key='test';instance.register_blueprint(zarzad_bp)
    instance.jinja_loader=ChoiceLoader([DictLoader({'layout.html':'{% block content %}{% endblock %}'}),instance.jinja_loader])
    return instance


def test_template_shows_order_batch_stage_sequence_and_actual_time():
    from flask import render_template
    instance=app();report=DosingTimeReportService.build([order()],[stage(1,1)])
    report.update(start='2026-10-01',end='2026-10-27',line='AGRO')
    with instance.test_request_context('/'):
        html=render_template('production/dosing_times_report.html',report=report,asset_version='test')
    assert 'MILK SPECJAL' in html and 'Szarża 1' in html
    assert 'Kolejność procesu' in html and 'Kolejność START' in html
    assert '00:10:00' in html and 'Naważanie' in html


@pytest.mark.parametrize('query',['od=wrong','od=2026-10-27&do=2026-10-01','od=2024-01-01&do=2026-10-27'])
def test_invalid_range_is_rejected_before_reading_database(query):
    instance=app();client=instance.test_client()
    with client.session_transaction() as state:state.update(zalogowany=True,rola='masteradmin')
    with patch('app.services.dosing_time_report_service.DosingTimeReportService.load') as load:
        response=client.get('/raporty/czasy-wydozowan?'+query)
    assert response.status_code==400
    load.assert_not_called()


def test_csv_contains_stage_sequence_and_protects_formula_strings():
    instance=app();client=instance.test_client()
    with client.session_transaction() as state:state.update(zalogowany=True,rola='masteradmin')
    plan=order();plan['produkt']='=FORMULA'
    report=DosingTimeReportService.build([plan],[stage(1,1)])
    with patch('app.services.dosing_time_report_service.DosingTimeReportService.load',return_value=report):
        response=client.get('/raporty/czasy-wydozowan?format=csv')
    assert response.status_code==200
    text=response.get_data(as_text=True)
    assert "'=FORMULA" in text and 'Kolejność START' in text and 'Naważanie' in text


def test_paused_stage_without_pause_start_is_unknown_not_counted_as_work():
    result=DosingTimeReportService.build([order()],[stage(1,1,stop=None,is_paused=1)],now=datetime(2026,10,27,10))
    row=result['orders'][0]['batches'][0]['stages'][0]
    assert row['work_s'] is None
    assert row['issue']=='Brak początku aktywnej pauzy'


def test_date_range_excludes_old_open_stages_and_includes_both_boundary_days():
    import sqlite3
    database=sqlite3.connect(':memory:')
    database.row_factory=sqlite3.Row
    database.executescript("""
        CREATE TABLE plans(id INTEGER,produkt TEXT,data_planu TEXT,status TEXT,sekcja TEXT,is_deleted INTEGER);
        INSERT INTO plans VALUES
        (1,'Old','2026-10-01','w toku','Zasyp',0),
        (2,'First','2026-10-22','w toku','Zasyp',0),
        (3,'Last','2026-10-27','w toku','Zasyp',0),
        (4,'Future','2026-10-28','w toku','Zasyp',0);
        CREATE TABLE zasyp_etapy(plan_id INTEGER,linia TEXT,etap INTEGER,czas_start TEXT,czas_stop TEXT);
        INSERT INTO zasyp_etapy VALUES(1,'AGRO',1,'2026-10-01 08:00:00',NULL);
    """)
    connection=MagicMock();cursor=connection.cursor.return_value
    def result():
        sql,args=cursor.execute.call_args.args if len(cursor.execute.call_args.args)==2 else (cursor.execute.call_args.args[0],())
        if sql.startswith('SHOW'):return [dict(Field='id')]
        if sql.startswith('SELECT p.id'):
            return [dict(row) for row in database.execute(sql.replace('%s','?'),tuple(value.isoformat() if hasattr(value,'isoformat') else value for value in args))]
        return []
    cursor.fetchall.side_effect=result
    try:
        with patch('app.services.dosing_time_report_service.get_db_connection',return_value=connection),patch('app.services.dosing_time_report_service.get_table_name',return_value='plans'):
            report=DosingTimeReportService.load(date(2026,10,22),date(2026,10,27),'AGRO',now=datetime(2026,10,27,12))
        assert [row['id'] for row in report['orders']]==[2,3]
        assert [row['key'] for row in report['options']]==['AGRO:2','AGRO:3']
    finally:
        database.close()
