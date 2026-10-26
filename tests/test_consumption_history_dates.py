from datetime import date, datetime
from unittest.mock import MagicMock, patch
import pytest
from flask import Flask
from app.services.production_consumption_service import ProductionConsumptionService


@pytest.fixture
def client():
    from app.blueprints.warehouse_v2.production_consumption_routes import api_zuzycie_history, zuzycie_view
    app=Flask(__name__)
    app.secret_key='history-test'
    app.add_url_rule('/history',view_func=api_zuzycie_history)
    app.add_url_rule('/zuzycie',endpoint='warehouse_v2.zuzycie_view',view_func=zuzycie_view)
    return app.test_client()


def login(client, role, name='personal-login'):
    with client.session_transaction() as state:
        state.update(zalogowany=True,login=name,rola=role)


def test_masteradmin_searches_selected_day_for_all_workers(client):
    login(client,'masteradmin')
    with patch.object(ProductionConsumptionService,'get_daily_consumption_history',return_value=[]) as load:
        response=client.get('/history?data=2026-08-12')
    assert response.status_code==200
    assert response.json['date']=='2026-08-12'
    load.assert_called_once_with(worker_login='personal-login',history_date=date(2026,8,12),all_workers=True)


@pytest.mark.parametrize('role',['admin','zarzad','lider','pracownik','magazynier'])
def test_date_search_is_enforced_server_side_for_masteradmin_only(client,role):
    login(client,role)
    with patch.object(ProductionConsumptionService,'get_daily_consumption_history') as load:
        assert client.get('/history?data=2026-08-12').status_code==403
        assert client.get('/zuzycie?data=2026-08-12').status_code==403
    load.assert_not_called()


def test_name_masteradmin_does_not_grant_date_search(client):
    login(client,'pracownik','masteradmin')
    assert client.get('/history?data=2026-08-12').status_code==403


@pytest.mark.parametrize('value',['invalid','2026-02-30','20260812','9999-12-31'])
def test_bad_date_is_rejected_before_query(client,value):
    login(client,'masteradmin')
    with patch.object(ProductionConsumptionService,'get_daily_consumption_history') as load:
        assert client.get('/history?data='+value).status_code==400
    load.assert_not_called()


def test_other_employee_keeps_today_and_own_history(client):
    login(client,'pracownik')
    with patch.object(ProductionConsumptionService,'get_daily_consumption_history',return_value=[]) as load:
        assert client.get('/history').status_code==200
    load.assert_called_once_with(worker_login='personal-login',history_date=date.today(),all_workers=False)


def test_view_passes_selected_date_and_filter_permission_to_template(client):
    login(client,'masteradmin')
    with patch.object(ProductionConsumptionService,'get_daily_consumption_history',return_value=[]), \
         patch('app.blueprints.warehouse_v2.production_consumption_routes.render_template',return_value='ok') as render:
        assert client.get('/zuzycie?data=2026-08-12&linia=AGRO').status_code==200
    assert render.call_args.kwargs['history_date']=='2026-08-12'
    assert render.call_args.kwargs['can_search_history'] is True


@pytest.mark.parametrize('all_workers',[True,False])
def test_history_query_binds_day_boundaries_and_preserves_scope(all_workers):
    connection=MagicMock()
    cursor=connection.cursor.return_value
    cursor.fetchall.return_value=[{'data_archiwizacji':datetime(2026,8,12,23,59,59)}]
    with patch('app.services.production_consumption_service.get_db_connection',return_value=connection):
        rows=ProductionConsumptionService.get_daily_consumption_history(worker_login='operator',history_date=date(2026,8,12),all_workers=all_workers)
    sql,values=cursor.execute.call_args.args
    assert values[:2]==(datetime(2026,8,12),datetime(2026,8,13))
    assert ('AND user_login = %s' in sql)==(not all_workers)
    assert values[-1]==100
    assert rows[0]['date']=='2026-08-12'
    assert rows[0]['time']=='23:59:59'
    connection.commit.assert_not_called()
    connection.close.assert_called_once()


def configure_real_history_template(app):
    from pathlib import Path
    from jinja2 import ChoiceLoader, DictLoader, FileSystemLoader
    root=Path(__file__).resolve().parents[1]
    app.jinja_loader=ChoiceLoader([
        DictLoader({'layout.html':'{% block content %}{% endblock %}', 'includes/qr_scanner_modal.html':''}),
        FileSystemLoader(str(root/'templates'))
    ])
    app.jinja_env.globals['url_for']=lambda endpoint,**kwargs:'/route/'+endpoint


@pytest.mark.parametrize('role,query,search_flag',[('masteradmin','?data=2026-10-22','true'),('pracownik','','false')])
def test_history_page_really_renders_json_configuration(client,role,query,search_flag):
    login(client,role)
    configure_real_history_template(client.application)
    with patch.object(ProductionConsumptionService,'get_daily_consumption_history',return_value=[]):
        response=client.get('/zuzycie'+query)
    assert response.status_code==200
    html=response.get_data(as_text=True)
    assert 'window.CAN_SEARCH_CONSUMPTION_HISTORY = '+search_flag+';' in html
    if role=='masteradmin':
        assert 'window.CONSUMPTION_HISTORY_DATE = "2026-10-22";' in html
        assert 'value="2026-10-22"' in html
    else:
        assert 'id="consumptionHistoryDate"' not in html


def test_history_template_handles_legacy_call_without_history_parameters(client):
    from flask import render_template
    configure_real_history_template(client.application)
    with client.application.test_request_context('/zuzycie'):
        html=render_template('warehouse_v2/zuzycie.html',daily_history=[],linia='ALL')
    assert 'window.CAN_SEARCH_CONSUMPTION_HISTORY = false;' in html
    assert 'window.CONSUMPTION_HISTORY_DATE = "";' in html
