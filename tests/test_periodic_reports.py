# cspell:words apexcharts
"""Periodic reports keep stages distinct, unknown values visible and reads side-effect free."""
from datetime import datetime
from unittest.mock import MagicMock,patch
import pytest
from flask import Flask
from jinja2 import ChoiceLoader,DictLoader
from app.services.periodic_report_service import PeriodicReportService


def order(id=1,section='Zasyp',mass=1000,plan=1200,day='2026-10-03',status='zakonczone',line='AGRO',**extra):
    extra.setdefault('czas_pracy_sekundy',7200)
    return dict(id=id,sekcja=section,tonaz=plan,tonaz_rzeczywisty=mass,data_planu=day,status=status,linia=line,produkt='Test product',real_start=datetime(2026,10,3,8),real_stop=datetime(2026,10,3,10),**extra)


def test_stage_totals_are_separate_and_pending_deleted_not_in_execution():
    result=PeriodicReportService.build([order(),order(id=2,section='Workowanie',mass=900),order(id=3,status='w toku',mass=5000)],[],2026,10,include_live=False)
    assert result['sections']['Zasyp']['actual']==1000
    assert result['sections']['Workowanie']['actual']==900
    assert result['annual']['Zasyp'][9]==1000
    assert result['annual']['Workowanie'][9]==900
    assert result['sections']['Zasyp']['count']==1


def test_missing_execution_is_not_replaced_by_plan_and_zero_is_a_real_value():
    result=PeriodicReportService.build([order(mass=None),order(id=2,section='Workowanie',mass=0)],[],2026,10)
    zasyp=result['sections']['Zasyp']
    assert zasyp['actual'] is None and zasyp['percent'] is None
    assert zasyp['missing_actual']==1 and zasyp['daily'][2]['actual'] is None
    assert result['sections']['Workowanie']['actual']==0
    assert result['sections']['Workowanie']['percent']==0


def test_learning_curve_uses_weighted_hours_not_mean_of_rates():
    rows=[order(mass=1000),order(id=2,mass=4000)]
    rows[1]['real_stop']=datetime(2026,10,3,12)
    rows[1]['czas_pracy_sekundy']=14400
    result=PeriodicReportService.build(rows,[],2026,10)['sections']['Zasyp']
    assert result['learning'][-1]['cumulative']==833.33
    assert result['rate']==833.3
    assert result['timed_count']==2
    rows[1]['real_stop']=None
    result=PeriodicReportService.build(rows,[],2026,10)['sections']['Zasyp']
    assert next(row for row in result['learning'] if row['id']==2)['rate'] is None
    assert result['timed_count']==1


def test_january_compares_to_previous_december_and_filters_products():
    current=order(mass=2000,day='2026-01-05')
    previous=order(id=2,mass=1000,day='2025-12-10')
    excluded=order(id=3,mass=9000,day='2026-01-05');excluded['produkt']='Different'
    result=PeriodicReportService.build([current,previous,excluded],[],2026,1,product='Test product')
    assert result['sections']['Zasyp']['change']==100
    assert result['annual']['Zasyp'][0]==2000
    assert 'Different' in result['products']


def test_excel_and_downtime_remain_separate_from_machine_execution():
    rows=[order(zasyp_excel_kg=1050)]
    downtime=[dict(sekcja='Zasyp',data_przestoju='2026-10-03',kategoria='Mechanical',czas_trwania_min=30,produkt='Test product'),
              dict(sekcja='Workowanie',data_przestoju='2026-10-03',kategoria='Mechanical',czas_trwania_min=60,produkt='Test product'),
              dict(sekcja='Zasyp',data_przestoju='2026-10-03',kategoria='Open',czas_trwania_min=None,produkt='Test product')]
    result=PeriodicReportService.build(rows,downtime,2026,10)
    assert result['sections']['Zasyp']['excel']==1050
    assert result['sections']['Zasyp']['actual']==1000
    assert result['sections']['Zasyp']['downtime_minutes']==30
    assert result['sections']['Zasyp']['missing_durations']==1
    assert result['sections']['Workowanie']['downtime_minutes']==60


def test_loader_uses_only_reads_and_no_mail_queries_or_schema_changes():
    conn=MagicMock();cursor=conn.cursor.return_value
    def rows():
        sql=cursor.execute.call_args.args[0]
        return [{'Field':field} for field in ['id','is_deleted','typ_zlecenia']] if sql.startswith('SHOW') else []
    cursor.fetchall.side_effect=rows
    with patch('app.services.periodic_report_service.get_db_connection',return_value=conn):
        result=PeriodicReportService.load(2026,10,'ALL')
    assert result['sections']['Zasyp']['count']==0
    for call in cursor.execute.call_args_list:
        sql=call.args[0]
        assert sql.startswith(('SHOW','SELECT'))
        assert 'auto_report_history' not in sql
        if 'FROM plan_' in sql and sql.startswith('SELECT'):
            assert 'is_deleted' in sql and "!= 'jakosc'" in sql
    conn.commit.assert_not_called();conn.close.assert_called_once()


def app():
    from app.blueprints.zarzad.base import zarzad_bp
    instance=Flask(__name__,template_folder='../templates',static_folder='../static');instance.secret_key='period-test'
    instance.register_blueprint(zarzad_bp)
    instance.jinja_loader=ChoiceLoader([DictLoader({'layout.html':'{% block content %}{% endblock %}'}),instance.jinja_loader])
    return instance


def test_page_contains_stage_views_month_navigation_and_no_email_history():
    instance=app()
    report=PeriodicReportService.build([order(),order(section='Workowanie',id=2)],[],2026,10)
    with instance.test_request_context('/'):
        from flask import render_template
        html=render_template('raporty_okresowe.html',report=report,section='Zasyp',static_version='test')
    assert 'panelZasyp' in html and 'panelWorkowanie' in html
    assert html.count('data-chart-expand=')==11
    assert 'periodChartDialog' in html
    assert html.count('data-month=')==12
    assert 'Historia E-mail' not in html and 'odbiorcy' not in html
    assert 'Krzywa tempa procesu' in html
    assert 'vendor/chart.min.js' in html
    assert 'apexcharts' not in html


@pytest.mark.parametrize('query',['rok=10000','miesiac=13','miesiac=0'])
def test_invalid_period_is_rejected_before_database_access(query):
    instance=app()
    client=instance.test_client()
    with client.session_transaction() as state:state.update(zalogowany=True,rola='masteradmin',grupa='ALL')
    with patch('app.services.periodic_report_service.PeriodicReportService.load') as load:
        response=client.get('/raporty_okresowe?'+query)
    assert response.status_code==400
    load.assert_not_called()


def test_csv_uses_selected_section_and_neutralizes_formula_product_names():
    instance=app();row=order(section='Workowanie');row['produkt']='=FORMULA'
    report=PeriodicReportService.build([row,order(id=2)],[],2026,10)
    client=instance.test_client()
    with client.session_transaction() as state:state.update(zalogowany=True,rola='masteradmin',grupa='ALL')
    with patch('app.services.periodic_report_service.PeriodicReportService.load',return_value=report):
        response=client.get('/raporty_okresowe?format=csv&sekcja=Workowanie')
    assert response.status_code==200
    text=response.get_data(as_text=True)
    assert "'=FORMULA" in text
    assert 'Workowanie;AGRO' in text and 'Zasyp;AGRO' not in text


def test_missing_downtime_register_is_unknown_instead_of_zero():
    report=PeriodicReportService.build([],[],2026,10,warnings=['Brak rejestru przestojów: AGRO / Zasyp'])
    assert report['sections']['Zasyp']['downtime_minutes'] is None
    assert report['sections']['Workowanie']['downtime_minutes']==0


def test_report_mail_history_is_read_only_and_keeps_legacy_files():
    from app.services.report_delivery_history import load_report_deliveries
    conn=MagicMock();cursor=conn.cursor.return_value
    cursor.fetchall.return_value=[dict(linia='AGRO',data_raportu='2026-10-26'),dict(linia='OTHER',data_raportu='invalid')]
    with patch('app.services.report_delivery_history.get_db_connection',return_value=conn):
        rows,available=load_report_deliveries('AGRO')
    assert available and rows[0]['pdf_filename']=='Raport_AGRO_2026-10-26.pdf'
    assert rows[1]['pdf_filename'] is None
    assert cursor.execute.call_args.args[0].startswith('SELECT')
    assert cursor.execute.call_args.args[1]==('AGRO',)
    conn.commit.assert_not_called()


def test_mail_report_tab_preserves_admin_role_guards():
    from app.blueprints.admin import admin_bp
    instance=Flask(__name__);instance.secret_key='test';instance.register_blueprint(admin_bp)
    instance.jinja_loader=DictLoader({'errors/403.html':'Denied'})
    client=instance.test_client()
    with client.session_transaction() as state:state.update(zalogowany=True,rola='operator',login='test')
    with patch('app.services.report_delivery_history.load_report_deliveries') as load:
        response=client.get('/admin/ustawienia/poczta?tab=raporty')
    assert response.status_code==403
    load.assert_not_called()


def test_report_delivery_history_is_rendered_inside_mail_settings_navigation():
    from app.blueprints.admin import admin_bp
    instance=app();instance.register_blueprint(admin_bp)
    instance.jinja_env.globals['role_has_access']=lambda key:True
    client=instance.test_client()
    with client.session_transaction() as state:state.update(zalogowany=True,rola='masteradmin',login='test')
    row=dict(data_raportu='2026-10-26',linia='AGRO',typ_raportu='Daily',odbiorcy='recipient@example.test',created_at='2026-10-26',pdf_filename=None,xls_filename=None)
    with patch('app.services.report_delivery_history.load_report_deliveries',return_value=([row],True)):
        response=client.get('/admin/ustawienia/poczta?tab=raporty')
    assert response.status_code==200
    html=response.get_data(as_text=True)
    assert 'E-mail i powiadomienia' in html
    assert 'Historia wysyłek raportów' in html
    assert 'Brak zapisanego potwierdzenia' in html


def test_live_totals_include_running_and_suspended_but_not_planned_orders():
    rows=[order(mass=1000),order(id=2,status='w toku',mass=5000),order(id=3,status='zawieszone',mass=2000),order(id=4,status='zaplanowane',mass=99999)]
    result=PeriodicReportService.build(rows,[],2026,10)['sections']['Zasyp']
    assert result['actual']==8000
    assert result['live_count']==2 and result['closed_count']==1
    assert result['count']==3
    assert len(result['learning'])==1
    assert result['timed_count']==1
    assert any(row['status']=='w toku' for row in result['details'])


def test_live_json_preserves_filter_and_reports_in_progress_status():
    instance=app();client=instance.test_client()
    with client.session_transaction() as state:state.update(zalogowany=True,rola='masteradmin',grupa='ALL')
    report=PeriodicReportService.build([order(status='w toku',mass=5000)],[],2026,10)
    with patch('app.services.periodic_report_service.PeriodicReportService.load',return_value=report) as load, patch('app.services.warehouse_live_updates.revision',return_value='v1'):
        response=client.get('/raporty_okresowe?format=json&linia=AGRO&produkt=Test&zakres=live')
    assert response.status_code==200
    assert response.json['report']['sections']['Zasyp']['live_count']==1
    assert response.json['report']['revision']=='v1'
    assert response.headers['Cache-Control']=='no-store'
    assert load.call_args.kwargs['include_live'] is True
    assert load.call_args.args[3]=='Test'


def test_completed_only_filter_is_passed_to_service():
    instance=app();client=instance.test_client()
    with client.session_transaction() as state:state.update(zalogowany=True,rola='masteradmin',grupa='ALL')
    report=PeriodicReportService.build([],[],2026,10,include_live=False)
    with patch('app.services.periodic_report_service.PeriodicReportService.load',return_value=report) as load:
        response=client.get('/raporty_okresowe?format=json&zakres=closed')
    assert response.status_code==200
    assert load.call_args.kwargs['include_live'] is False


def test_periodic_asset_version_changes_when_chart_script_changes(tmp_path):
    from app.core.contexts import _compute_periodic_ui_version
    for name in ('static/js/periodic_reports.js','static/css/periodic_reports.css','templates/raporty_okresowe.html'):
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('before',encoding='utf-8')
    instance=Flask(__name__,static_folder=str(tmp_path/'static'))
    with instance.app_context():
        before=_compute_periodic_ui_version()
        (tmp_path/'static/js/periodic_reports.js').write_text('after',encoding='utf-8')
        assert _compute_periodic_ui_version()!=before


def test_continued_work_order_is_split_between_actual_pallet_days():
    old=order(id=368,section='Workowanie',mass=21400,plan=21400,day='2026-10-26')
    old['production_events']=[dict(date='2026-10-26',kg=15000),dict(date='2026-10-27',kg=6400)]
    new=order(id=370,section='Workowanie',mass=5000,plan=7841.75,day='2026-10-27',status='w toku')
    new['production_events']=[dict(date='2026-10-27',kg=5000)]
    report=PeriodicReportService.build([old,new],[],2026,10)['sections']['Workowanie']
    assert report['daily'][25]['actual']==15000
    assert report['daily'][26]['actual']==11400
    assert report['daily'][26]['continuation']==6400
    assert report['daily'][26]['plan']==7841.75
    assert report['actual']==26400
    assert sum(day['actual'] or 0 for day in report['daily'])==report['actual']


def test_pallets_crossing_month_boundary_are_not_counted_twice():
    row=order(section='Workowanie',mass=10000,plan=10000,day='2026-09-30')
    row['production_events']=[dict(date='2026-09-30',kg=7000),dict(date='2026-10-01',kg=3000)]
    report=PeriodicReportService.build([row],[],2026,10)
    assert report['annual']['Workowanie'][8:10]==[7000,3000]
    work=report['sections']['Workowanie']
    assert work['actual']==3000 and work['plan']==0
    assert work['details'][0]['total_actual']==10000
    assert work['details'][0]['percent']==100


def test_loader_uses_the_linked_zasyp_weight_for_workowanie_plan():
    conn=MagicMock();cursor=conn.cursor.return_value
    def rows():
        sql=cursor.execute.call_args.args[0]
        if sql.startswith('SHOW'):return [dict(Field=field) for field in ['id','zasyp_id','is_deleted','typ_zlecenia']]
        if sql.startswith('SELECT p.id'):
            row=order(id=370,section='Workowanie',mass=5000,plan=4611.48,day='2026-10-27',status='w toku')
            row['linked_zasyp_kg']=7841.75
            return [row]
        if sql.startswith('SELECT plan_id,DATE'):return [dict(plan_id=370,production_date='2026-10-27',kg=5000)]
        return []
    cursor.fetchall.side_effect=rows
    with patch('app.services.periodic_report_service.get_db_connection',return_value=conn):
        result=PeriodicReportService.load(2026,10,'AGRO')
    row=result['sections']['Workowanie']['details'][0]
    assert row['plan']==7841.75 and row['actual']==5000
    assert result['sections']['Workowanie']['daily'][26]['plan']==7841.75
    conn.commit.assert_not_called()


def test_details_follow_plan_dates_while_curve_follows_completion_dates():
    earlier=order(id=1,day='2026-10-23');earlier['real_stop']=datetime(2026,10,27,10)
    later=order(id=2,day='2026-10-26');later['real_stop']=datetime(2026,10,26,10)
    stage=PeriodicReportService.build([earlier,later],[],2026,10)['sections']['Zasyp']
    assert [row['id'] for row in stage['details']]==[1,2]
    assert [row['id'] for row in stage['learning']]==[2,1]
    point=stage['learning'][0]
    assert point['product']=='Test product' and point['date']=='2026-10-26'
    assert point['label']=='Test product · 26.10.2026 · AGRO'


def test_zasyp_continuation_counts_actual_batch_days_not_only_new_order():
    old=order(id=367,mass=21558.9,plan=22000,day='2026-10-26',status='zawieszone')
    old['production_events']=[dict(date='2026-10-26',kg=15323.3),dict(date='2026-10-27',kg=6235.6)]
    new=order(id=369,mass=7841.75,plan=10000,day='2026-10-27',status='zawieszone')
    new['production_events']=[dict(date='2026-10-27',kg=7841.75)]
    stage=PeriodicReportService.build([old,new],[],2026,10)['sections']['Zasyp']
    today=stage['daily'][26]
    assert today['actual']==14077.35
    assert today['plan']==10000
    assert today['continuation']==6235.6
    assert stage['actual']==29400.65
    assert round(sum(day['actual'] or 0 for day in stage['daily']),3)==stage['actual']


def test_zasyp_event_query_uses_confirmed_doses_and_consumed_buckets():
    conn=MagicMock();cursor=conn.cursor.return_value
    def rows():
        sql=cursor.execute.call_args.args[0]
        if sql.startswith('SHOW'):return [dict(Field='id')]
        if sql.startswith('SELECT p.id'):return [order(id=369,day='2026-10-27',mass=7841.75,plan=10000,status='zawieszone')]
        if sql.startswith('SELECT plan_id,production_date'):return [dict(plan_id=369,production_date='2026-10-27',kg=7841.75,fallback_dates=0)]
        return []
    cursor.fetchall.side_effect=rows
    with patch('app.services.periodic_report_service.get_db_connection',return_value=conn):
        stage=PeriodicReportService.load(2026,10,'AGRO')['sections']['Zasyp']
    assert stage['daily'][26]['actual']==7841.75
    sql=next(call.args[0] for call in cursor.execute.call_args_list if call.args[0].startswith('SELECT plan_id,production_date'))
    assert 'd.potwierdzone=1' in sql and 'COALESCE(d.anulowana,0)=0' in sql
    assert "w.status='wrzucone_do_mieszalnika'" in sql and 'UPPER(w.linia)=%s' in sql
    conn.commit.assert_not_called()


def test_daily_staffing_is_unique_by_section_date_and_hall_with_missing_unknown():
    assignments=[dict(date='2026-10-03',sekcja='Zasyp',linia=hall,pracownik_id=person)
                 for hall,person in [('AGRO',1),('AGRO',1),('PSD',1),('PSD',2)]]
    assignments += [dict(date='2026-10-03',sekcja='Workowanie',linia='AGRO',pracownik_id=3),
                    dict(date='2026-09-03',sekcja='Zasyp',linia='AGRO',pracownik_id=4)]
    report=PeriodicReportService.build([order()],[],2026,10,line='ALL',staffing=assignments)
    assert report['sections']['Zasyp']['daily'][2]['staff_count']==3
    assert report['sections']['Workowanie']['daily'][2]['staff_count']==3
    assert report['sections']['Zasyp']['daily'][3]['staff_count'] is None
    report=PeriodicReportService.build([order()],[],2026,10,line='AGRO',product='Other',staffing=assignments)
    assert report['sections']['Zasyp']['daily'][2]['staff_count']==2


def test_staffing_maps_agro_operator_roles_to_production_sections():
    assignments=[dict(date='2026-10-03',sekcja=role,linia='AGRO',pracownik_id=index)
                 for index,role in enumerate(['Operator sterowni','Operator zasypów 1','Operator zasypów 2','Operator workowania','Technik utrzymania Ruchu'])]
    report=PeriodicReportService.build([],[],2026,10,staffing=assignments)
    assert report['sections']['Zasyp']['daily'][2]['staff_count']==4
    assert report['sections']['Workowanie']['daily'][2]['staff_count']==4


def test_dashboard_production_headcount_on_reported_days():
    staffing=[]
    for day,roles in [('2026-10-23',['Operator sterowni','Operator workowania','Operator zasypów 1','Technik utrzymania Ruchu']),('2026-10-26',['Operator sterowni','Operator workowania','Operator zasypów 1','Operator zasypów 2']),('2026-10-27',['Operator sterowni','Operator workowania'])]:
        staffing.extend(dict(date=day,sekcja=role,linia='AGRO',pracownik_id=index) for index,role in enumerate(roles))
    result=PeriodicReportService.build([],[],2026,10,line='ALL',staffing=staffing)
    for section in ['Zasyp','Workowanie']:
        assert [result['sections'][section]['daily'][day-1]['staff_count'] for day in [23,26,27]]==[3,4,2]


def test_all_halls_staffing_retains_separate_daily_counts():
    staffing=[dict(date='2026-09-01',sekcja='Workowanie',linia=hall,pracownik_id=offset+i) for hall,total,offset in [('AGRO',3,0),('PSD',6,10)] for i in range(total)]
    report=PeriodicReportService.build([],[],2026,9,line='ALL',staffing=staffing)
    for section in ['Zasyp','Workowanie']:
        assert report['sections'][section]['daily'][0]['staff_by_hall']=={'AGRO':3,'PSD':6}
        assert report['sections'][section]['daily'][1]['staff_by_hall']=={'AGRO':None,'PSD':None}


@pytest.mark.parametrize('seconds',[None,0,-1,99999999])
def test_no_calendar_fallback_when_confirmed_work_time_is_missing_or_invalid(seconds):
    row=order(czas_pracy_sekundy=seconds)
    row['real_stop']=datetime(2026,10,6,10)
    section=PeriodicReportService.build([row],[],2026,10)['sections']['Zasyp']
    assert section['rate'] is not None
    assert 'Wyliczony' in section['learning'][0]['time_basis']


def test_confirmed_work_time_excludes_weekend_from_rate():
    row=order(mass=16206,czas_pracy_sekundy=23206)
    row['real_start']=datetime(2026,10,23,11,55,54)
    row['real_stop']=datetime(2026,10,26,10,30,29)
    section=PeriodicReportService.build([row],[],2026,10)['sections']['Zasyp']
    assert section['learning'][0]['rate']==2514.07


def test_partial_counter_shorter_than_final_work_segment_does_not_inflate_rate():
    row=order(mass=12400,czas_pracy_sekundy=15,ostatnie_wznowienie=datetime(2026,10,6,8,54,35))
    row['real_start']=datetime(2026,10,6,7,40,34)
    row['real_stop']=datetime(2026,10,6,13,0,36)
    section=PeriodicReportService.build([row],[],2026,10)['sections']['Zasyp']
    point=section['learning'][0]
    assert point['rate']<3000
    assert 'Wyliczony' in point['time_basis']


def test_packing_ready_big_bags_does_not_count_as_batch_production():
    rows=[order(id=1,has_recorded_batches=False),order(id=2,has_recorded_batches=True),order(id=3,section='Workowanie',has_recorded_batches=False)]
    report=PeriodicReportService.build(rows,[],2026,10)
    zasyp=report['sections']['Zasyp']
    assert [row['id'] for row in zasyp['details']]==[2]
    assert [row['id'] for row in zasyp['learning']]==[2]
    assert zasyp['actual']==1000 and zasyp['plan']==1200
    assert report['annual']['Zasyp'][9]==1000
    assert [row['id'] for row in report['sections']['Workowanie']['details']]==[3]


def test_shift_time_excludes_nights_and_weekends_but_preserves_overtime_stop():
    from app.services.periodic_report_service import scheduled_work_seconds
    assert scheduled_work_seconds(datetime(2026,10,23,12),datetime(2026,10,26,10))==6*3600
    assert scheduled_work_seconds(datetime(2026,10,27,12),datetime(2026,10,28,16,30))==12.5*3600
    assert scheduled_work_seconds(datetime(2026,10,28,7),datetime(2026,10,28,16))==9*3600
    assert scheduled_work_seconds(None,datetime(2026,10,28,16)) is None
