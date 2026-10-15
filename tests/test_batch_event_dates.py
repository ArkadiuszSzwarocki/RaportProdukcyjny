"""Production history uses actual event dates, including stages spanning midnight."""
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from flask import Flask
from jinja2 import ChainableUndefined
import pytest

from app.services.production_service import ProductionService
from app.services.zasyp_etapy_service import ZasypEtapyService
from app.services.zasyp_etapy_support import EtapRow


def test_stage_dates_can_differ_without_changing_time_editor_values():
    row = EtapRow(2, datetime(2026, 10, 14, 23, 55), datetime(2026, 10, 15, 0, 12), 'operator', 'operator')
    payload = ZasypEtapyService._build_etapy_payload(323, 'AGRO', 10, {2: row})
    stage = next(s for s in payload['etapy'] if s['etap'] == 2)
    assert stage['czas_start_str'] == '23:55'
    assert stage['czas_stop_str'] == '00:12'
    assert stage['data_start_str'] == '14.10.2026'
    assert stage['data_stop_str'] == '15.10.2026'
    app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1] / 'templates'))
    env = app.jinja_env.overlay(undefined=ChainableUndefined)
    env.add_extension('jinja2.ext.do')
    env.globals = dict(env.globals, role_is_readonly=lambda key: False, url_for=lambda endpoint, **kw: '/action')
    with app.test_request_context('/'):
        html = env.get_template('dashboard/_dashboard_agro_stages.html').render(
            p=(323, 'Mix', 400, 'zakonczone'), linia='AGRO', sekcja='Zasyp', rola='masteradmin',
            etapy_sesje_mapa={323: [dict(szarza_nr=10, etapy=[stage], is_current=False)]})
    assert '14.10.2026 23:55' in html
    assert '15.10.2026 00:12' in html


@pytest.mark.parametrize('line', ['AGRO', 'PSD'])
def test_dashboard_preserves_batch_date_and_ids_for_individual_duplicate_cancellation(line):
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    def fetchall():
        query = cursor.execute.call_args.args[0]
        if 's.data_dodania' in query and 'COALESCE(s.uwagi' in query:
            return [(323, 558, 100, '00:12', 'zarejestrowana', 'operator', '', 10, datetime(2026, 10, 15, 0, 12))]
        if 'SELECT d.szarza_id' in query:
            return [(558, 'Mix', 55.4, 50, 91), (558, 'Mix', 55.4, 50, 92)]
        return []
    cursor.fetchall.side_effect = fetchall
    plan = [323, 'Mix', 400, 'w toku', None, None, 0, 210.8] + [None] * 23
    with patch('app.services.production_service.QueryHelper.get_plan_produkcji', return_value=[plan]), patch.object(
        ProductionService, '_get_transfer_map', return_value={}), patch.object(
        ProductionService, '_populate_carry_over_tonaz'), patch('app.services.production_service.refresh_bufor_queue'):
        _, batches, _, _ = ProductionService.get_production_plans(date(2026, 10, 14), 'Zasyp', line, cursor)
    batch = batches[323][0]
    assert batch[10] == '15.10.2026'
    assert [d[3] for d in batch[3]] == [91, 92]
    assert batch[0] == pytest.approx(210.8)
    app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1] / 'templates'))
    env = app.jinja_env.overlay(undefined=ChainableUndefined)
    env.add_extension('jinja2.ext.do')
    env.globals = dict(env.globals, role_is_readonly=lambda key: False, url_for=lambda endpoint, **kw: '/action')
    with app.test_request_context('/'):
        html = env.get_template('dashboard/_dashboard_agro_active_details.html').render(
            p=plan, linia=line, sekcja='Zasyp', rola='masteradmin', palety_mapa=batches)
    assert '15.10.2026 00:12' in html
    assert 'Anuluj #91' in html and 'Anuluj #92' in html
