import json
# cspell:ignore węwnętrzna
# Exact field label from the provider, including its spelling error.
from datetime import datetime
from io import BytesIO
from unittest.mock import patch

import pytest

from app.services import ipomiar_service as service
from scripts.sync_ipomiar import collect
from scripts.reports.measurement_sections import write_excel, render_pdf


@pytest.fixture
def config(tmp_path, monkeypatch):
    config = {'device': 'test-device', 'name': 'Agro', 'temperature': 'Temperatura węwnętrzna',
              'humidity': 'Wilgotności węwnętrzna', 'timezone': 'UTC', 'directory': tmp_path}
    monkeypatch.setattr(service, 'devices', lambda: [config])
    return config


def save(config, day, payload):
    samples = service.normalize(payload, day, config)
    path = service.archive_path(day, config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'day': day, 'device': config['device'], 'samples': samples}), encoding='utf-8')
    return samples


def row(time, temperature='20', humidity='50'):
    return {'Date': time, 'Temperatura węwnętrzna': temperature, 'Wilgotności węwnętrzna': humidity}


def test_local_day_includes_previous_utc_day(config):
    samples = service.normalize([row('2026-10-01 22:05:00'), row('2026-10-02 22:05:00')], '2026-10-02', config)
    assert len(samples) == 1
    assert samples[0]['time'] == '2026-10-02 00:05:00'


def test_missing_values_never_become_zero_and_duplicates_deduplicated(config):
    rows = [row('2026-10-02 10:00:00', 'nan', '105'), row('2026-10-02 10:05:00', None, '0'),
            row('2026-10-02 10:05:00', None, '0'), {'Date': 'invalid'}]
    samples = save(config, '2026-10-02', rows)
    assert len(samples) == 1
    result = service.read_day('2026-10-02', config=config)
    assert result['summary']['temperature'] is None
    assert result['summary']['humidity']['mean'] == 0
    assert result['summary']['humidity']['count'] == 1


def test_summary_counts_gaps_and_marks_stale(config):
    save(config, '2026-10-02', [row('2026-10-02 10:00:00', '10'), row('2026-10-02 10:20:00', '20')])
    result = service.read_day('2026-10-02', now=datetime(2026, 10, 2, 13, tzinfo=service.ZONE), config=config)
    assert result['summary']['temperature']['mean'] == 15
    assert result['summary']['temperature']['min'] == 10
    assert result['summary']['temperature']['max'] == 20
    assert result['gaps'] == 1
    assert result['stale']


def test_daily_report_never_borrows_old_measurements(config):
    save(config, '2026-07-03', [row('2026-07-03 10:12:00')])
    assert service.read_all('2026-10-02')[0]['latest'] is None


def test_daylight_saving_repeated_hour_preserved(config):
    samples = save(config, '2026-10-25', [row('2026-10-25 00:30:00'), row('2026-10-25 01:30:00')])
    assert len(samples) == 2
    assert samples[0]['time'] == samples[1]['time']
    assert len(service.read_day('2026-10-25', config=config)['samples']) == 2


def test_device_path_traversal_rejected(config):
    config['device'] = '../other'
    with pytest.raises(ValueError):
        service.archive_path('2026-10-02', config)


def test_failed_collection_preserves_archive(config):
    save(config, '2026-10-02', [row('2026-10-02 10:00:00')])
    before = service.archive_path('2026-10-02', config).read_bytes()
    with patch('requests.Session.get', side_effect=OSError('offline')):
        with pytest.raises(OSError):
            collect('2026-10-02', config)
    assert service.archive_path('2026-10-02', config).read_bytes() == before


def test_collection_merges_archive_and_fetches_previous_utc_day(config):
    from unittest.mock import MagicMock
    save(config, '2026-10-02', [row('2026-10-02 10:00:00')])
    response = MagicMock()
    response.status_code = 200
    response.iter_content.return_value = [json.dumps([row('2026-10-01 22:05:00'), row('2026-10-02 10:05:00')]).encode()]
    with patch('requests.Session') as session_class:
        session = session_class.return_value.__enter__.return_value
        session.get.return_value.__enter__.return_value = response
        assert collect('2026-10-02', config) == 3
        assert [call.kwargs['params']['date'] for call in session.get.call_args_list] == ['2026-10-01', '2026-10-02']
        assert session.trust_env is False
        assert all(call.kwargs['allow_redirects'] is False for call in session.get.call_args_list)
    assert len(service.read_day('2026-10-02', config=config)['samples']) == 3


def test_empty_or_redirected_response_preserves_archive(config):
    from unittest.mock import MagicMock
    save(config, '2026-10-02', [row('2026-10-02 10:00:00')])
    before = service.archive_path('2026-10-02', config).read_bytes()
    for status in (200, 302):
        response = MagicMock()
        response.status_code = status
        response.iter_content.return_value = [b'[]']
        with patch('requests.Session') as session_class:
            session_class.return_value.__enter__.return_value.get.return_value.__enter__.return_value = response
            with pytest.raises(ValueError):
                collect('2026-10-02', config)
        assert service.archive_path('2026-10-02', config).read_bytes() == before


def test_excel_and_pdf_include_both_measurements(config):
    import pandas as pd
    from fpdf import FPDF
    save(config, '2026-10-02', [row('2026-10-02 10:00:00')])
    values = service.read_all('2026-10-02')
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        write_excel(writer, values)
    assert pd.read_excel(output, sheet_name='Pomiary - Podsumowanie')['Liczba odczytów'].tolist() == [1, 1]
    pdf = FPDF()
    pdf.add_page()
    render_pdf(pdf, values)
    assert 'Temperatura' in str(pdf.pages[1])
    assert 'Wilgotnosc' in str(pdf.pages[1])


def test_template_escapes_sensor_name(config):
    from flask import Flask, render_template
    from pathlib import Path
    config['name'] = '<script>alert(1)</script>'
    save(config, '2026-10-02', [row('2026-10-02 10:00:00')])
    app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1] / 'templates'))
    with app.app_context():
        html = render_template('dashboard/_agro_measurement_values.html', measurements_list=service.read_all('2026-10-02'))
    assert '<script>' not in html
    assert '&lt;script&gt;' in html


@pytest.mark.parametrize('permission,group,expected', [(False, 'AGRO', 403), (True, 'PSD', 403), (True, 'AGRO', 200)])
def test_measurement_endpoint_obeys_page_and_hall_permissions(config, permission, group, expected):
    from flask import Flask
    from pathlib import Path
    from app.blueprints.main import agro_measurements
    app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1] / 'templates'))
    app.secret_key = 'test-only'
    app.add_url_rule('/measurements', view_func=agro_measurements)
    client = app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True, rola='pracownik', grupa=group)
    with patch('app.core.contexts.inject_role_permissions', return_value={'role_has_access': lambda key: permission}):
        response = client.get('/measurements?data=2026-10-02')
    assert response.status_code == expected
    if expected == 200:
        assert response.headers['Cache-Control'] == 'no-store'


def test_measurement_endpoint_rejects_invalid_date(config):
    from flask import Flask
    from app.blueprints.main import agro_measurements
    app = Flask(__name__)
    app.secret_key = 'test-only'
    app.add_url_rule('/measurements', view_func=agro_measurements)
    client = app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True, rola='masteradmin', grupa='ALL')
    with patch('app.core.contexts.inject_role_permissions', return_value={'role_has_access': lambda key: True}):
        assert client.get('/measurements?data=../../private').status_code == 400
