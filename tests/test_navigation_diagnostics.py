# cspell:words caplog Referer tojson
"""Diagnostic evidence is scoped, bounded, authenticated and credential-free."""
import json
from flask import Flask, render_template_string, session, redirect
import pytest
from app.core.navigation_diagnostics import register_navigation_diagnostics


@pytest.fixture
def diagnostic():
    app = Flask(__name__)
    app.secret_key = 'isolated-navigation-test'
    register_navigation_diagnostics(app)
    @app.get('/')
    @app.get('/agro/scanner/ui')
    def page():
        return render_template_string('{{ navigation_diagnostics | tojson }}'), 200, {'Content-Type': 'application/json'}
    @app.get('/jump')
    def jump():
        return redirect('/')
    client = app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True, login='SzwarArk', rola='lider', _account_role='lider')
    return client


def test_server_arrival_has_time_in_audit_and_no_query_values(diagnostic, caplog):
    response = diagnostic.get('/?linia=AGRO&sscc=secret-pallet', headers={
        'Referer':'http://localhost/agro/scanner/ui?code=secret-pallet', 'Sec-Fetch-User':'?1'})
    config = response.json
    assert len(config['event_id']) == 16
    assert 'server_arrival' in caplog.text and 'scanner' in caplog.text
    assert 'secret-pallet' not in caplog.text
    assert all(record.created > 0 for record in caplog.records)


def test_scanner_does_not_generate_dashboard_arrival(diagnostic, caplog):
    assert diagnostic.get('/agro/scanner/ui').json['event_id'] == ''
    assert 'server_arrival' not in caplog.text


def test_client_report_logs_only_allowlisted_data_and_correlates_event(diagnostic, caplog):
    config=diagnostic.get('/').json
    caplog.clear()
    response=diagnostic.post('/auth/navigation-diagnostics',json={
        'csrf':config['csrf'],'event_id':config['event_id'],'reason':'role_activated_elsewhere',
        'previous_view':'scanner','navigation_type':'navigate','previous_active':False,
        'observed_active':True,'observed_eligible':True,'page_age_ms':35000,
        'url':'secret-url','token':'secret-token','pallet':'secret-pallet'})
    assert response.status_code==200
    assert config['event_id'] in caplog.text and 'role_activated_elsewhere' in caplog.text
    assert 'secret-' not in caplog.text and config['csrf'] not in caplog.text
    assert diagnostic.post('/auth/navigation-diagnostics',json={'csrf':config['csrf']}).status_code==429


@pytest.mark.parametrize('token', ['', 'wrong', None, 1])
def test_report_rejects_missing_or_wrong_csrf(diagnostic,token,caplog):
    diagnostic.get('/agro/scanner/ui')
    assert diagnostic.post('/auth/navigation-diagnostics',json={'csrf':token}).status_code==403
    assert 'client_arrival' not in caplog.text


def test_diagnostic_is_not_available_to_other_accounts(diagnostic,caplog):
    with diagnostic.session_transaction() as state:
        state['login']='ordinary'
    assert diagnostic.get('/').json is None
    assert diagnostic.post('/auth/navigation-diagnostics',json={}).status_code==403
    assert 'NAVIGATION_DIAGNOSTIC' not in caplog.text


def test_reports_are_bounded_and_bad_fields_cannot_enter_logs(diagnostic,caplog):
    token=diagnostic.get('/agro/scanner/ui').json['csrf']
    assert diagnostic.post('/auth/navigation-diagnostics',json={'csrf':token,'padding':'x'*4096}).status_code==413
    response=diagnostic.post('/auth/navigation-diagnostics',json={'csrf':token,'reason':'secret\nline',
        'previous_view':'/scanner/secret','event_id':'secret','page_age_ms':float('inf')})
    assert response.status_code==200
    assert 'secret' not in caplog.text
    assert 'unattributed' in caplog.text


def test_server_redirect_to_dashboard_identifies_source_endpoint(diagnostic,caplog):
    assert diagnostic.get('/jump').status_code==302
    assert 'server_redirect' in caplog.text and 'jump' in caplog.text
    assert '302' in caplog.text


def test_background_dashboard_refresh_is_not_a_page_arrival(diagnostic,caplog):
    assert diagnostic.get('/',headers={'Sec-Fetch-Mode':'cors'}).json['event_id']==''
    assert 'server_arrival' not in caplog.text
