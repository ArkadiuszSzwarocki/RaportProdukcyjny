from datetime import datetime, date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.services.zasyp_etapy_service import ZasypEtapyService
from jinja2 import ChainableUndefined


@pytest.mark.parametrize('mixing_stage,next_stage', [(2, 3), (4, 31), (41, 32), (410, 311)])
def test_last_confirmation_stops_mixing_and_starts_next_addition(mixing_stage, next_stage):
    cursor = MagicMock()
    cursor.fetchone.side_effect = [(4,), (0,)]
    now = datetime(2026, 10, 11, 11)
    cursor.fetchall.return_value = [(mixing_stage, now, None, date(2026, 10, 11))]
    result = ZasypEtapyService.advance_after_confirmed_dosypka(cursor, 323, 558, 'test')
    assert result == next_stage
    queries = cursor.execute.call_args_list
    updates = [call for call in queries if call.args[0].startswith('UPDATE')]
    assert len(updates) == 2
    assert 'czas_stop=NOW()' in updates[0].args[0]
    assert updates[0].args[1] == ('test', 323, 4, mixing_stage)
    assert 'czas_start=NOW()' in updates[1].args[0]
    assert updates[1].args[1] == ('test', 323, 4, next_stage)
    pending = next(call for call in queries if 'SELECT COUNT(*)' in call.args[0])
    assert pending.args[1] == (323, 558)


@pytest.mark.parametrize('batch,stages,pending', [
    (None, [], 0),
    ((4,), [(1, datetime(2026, 10, 11, 11), None, date(2026, 10, 11))], 0),
    ((4,), [(2, datetime(2026, 10, 11, 11), None, date(2026, 10, 11))], 1),
    ((4,), [(2, datetime(2026, 10, 11, 11), datetime(2026, 10, 11, 12), date(2026, 10, 11))], 0),
])
def test_confirmation_does_not_advance_inactive_batch_or_remaining_pending_additions(batch, stages, pending):
    cursor = MagicMock()
    cursor.fetchone.side_effect = [batch, (pending,)]
    cursor.fetchall.return_value = stages
    assert ZasypEtapyService.advance_after_confirmed_dosypka(cursor, 323, 558, 'test') is None
    assert not any(call.args[0].startswith(('UPDATE', 'INSERT')) for call in cursor.execute.call_args_list)


@pytest.mark.parametrize('stage', [2, 4, 41, 410])
def test_stop_mixing_does_not_create_dosypka_pair(stage):
    connection = MagicMock()
    cursor = connection.cursor.return_value
    started = datetime(2026, 10, 11, 11)
    cursor.fetchone.return_value = (started, None)
    stages = [(stage, started, None, date(2026, 10, 11))]
    cursor.fetchall.side_effect = [[], stages]
    with patch('app.services.zasyp_etapy_service.get_db_connection', return_value=connection), patch.object(
        ZasypEtapyService, '_resolve_szarza_nr', return_value=3):
        ok, _ = ZasypEtapyService.stop_etap(323, 'AGRO', stage, 'test', szarza_nr=3)
    assert ok
    inserts = [call.args[1][4] for call in cursor.execute.call_args_list if 'INSERT INTO zasyp_etapy' in call.args[0]]
    assert inserts == []
    connection.commit.assert_called_once()


@pytest.mark.parametrize('stage', [5, 6])
def test_pending_addition_rejects_emptying_stop_without_writes(stage):
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchone.return_value = (datetime(2026, 10, 11, 11), None)
    cursor.fetchall.return_value = [(0,)]
    with patch('app.services.zasyp_etapy_service.get_db_connection', return_value=connection), patch.object(
        ZasypEtapyService, '_resolve_szarza_nr', return_value=3):
        ok, message = ZasypEtapyService.stop_etap(323, 'AGRO' if stage == 5 else 'PSD', stage, 'test', szarza_nr=3)
    assert not ok
    assert 'Najpierw potwierdź' in message
    assert not any(call.args[0].lstrip().startswith(('UPDATE', 'INSERT')) for call in cursor.execute.call_args_list)
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()


@pytest.mark.parametrize('stage', [2, 4, 41, 410])
def test_pending_addition_does_not_reject_mixing_stop(stage):
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchone.return_value = (datetime(2026, 10, 11, 11), None)
    cursor.fetchall.return_value = [(0,)]
    with patch('app.services.zasyp_etapy_service.get_db_connection', return_value=connection), patch.object(
        ZasypEtapyService, '_resolve_szarza_nr', return_value=3):
        ok, _ = ZasypEtapyService.stop_etap(323, 'AGRO', stage, 'test', szarza_nr=3)
    assert ok
    connection.commit.assert_called_once()


def test_repeated_stop_does_not_duplicate_pair():
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchone.return_value = (datetime(2026, 10, 11, 11), datetime(2026, 10, 11, 12))
    with patch('app.services.zasyp_etapy_service.get_db_connection', return_value=connection), patch.object(
        ZasypEtapyService, '_resolve_szarza_nr', return_value=3):
        ok, _ = ZasypEtapyService.stop_etap(323, 'AGRO', 2, 'test', szarza_nr=3)
    assert ok
    assert not any('INSERT' in call.args[0] for call in cursor.execute.call_args_list)


def test_batch_badge_is_rendered_only_on_assigned_batch(app):
    env = app.jinja_env.overlay(undefined=ChainableUndefined)
    env.globals = dict(env.globals, url_for=lambda endpoint, **kw: '/action/' + endpoint,
                       role_is_readonly=lambda key: False)
    plan = [None] * 32
    plan[:4] = [323, 'Produkt', 400, 'w toku']
    with app.test_request_context('/'):
        html = env.get_template('dashboard/_dashboard_agro_active_details.html').render(
            p=plan, linia='AGRO', sekcja='Zasyp', rola='masteradmin',
            palety_mapa={323: [(1000, '12:00', i) for i in (101, 102, 103)]},
            dosypki_oczekujace_mapa={323: 1, (323, 103): 1}, dzisiaj=date(2026, 10, 11))
    assert html.count('class="action-badge"') == 1
    import re
    button = re.search(r'<a[^>]*data-szarza-id="103".*?</a>', html, re.S)
    assert button and 'class="action-badge"' in button.group()


@pytest.mark.parametrize('pending,disabled', [(0, False), (1, True)])
def test_emptying_stop_button_uses_pending_count_for_its_batch(app, pending, disabled):
    env = app.jinja_env.overlay(undefined=ChainableUndefined)
    env.globals = dict(env.globals, url_for=lambda endpoint, **kw: '/action/' + endpoint,
                       role_is_readonly=lambda key: False)
    plan = [None] * 32
    plan[:4] = [323, 'Produkt', 400, 'w toku']
    stage = {'etap': 5, 'exists': True, 'is_running': True, 'czas_start': datetime(2026, 10, 11, 11)}
    with app.test_request_context('/'):
        html = env.get_template('dashboard/_dashboard_agro_stages.html').render(
            p=plan, linia='AGRO', sekcja='Zasyp', rola='masteradmin',
            etapy_sesje_mapa={323: [{'szarza_nr': 3, 'etapy': [stage], 'is_current': True, 'active_etap': 5}]},
            dosypki_oczekujace_mapa={('nr', 323, 3): pending, ('nr', 323, 1): 9},
            dosypki_mapa={323: [{'szarza_nr': 3, 'potwierdzono_dt': datetime(2026, 10, 11, 12)}]})
    import re
    button = re.search(r'<button[^>]*class="btn-action btn-stop"[^>]*>', html)
    assert button and ('disabled' in button.group()) == disabled
    assert ('STOP zablokowany: potwierdź dosypki do zasypu 3' in html) == disabled


@pytest.mark.parametrize('mixing_stage', [2, 4, 41, 410])
def test_mixing_stop_button_is_never_disabled_by_pending_dosypki(app, mixing_stage):
    env = app.jinja_env.overlay(undefined=ChainableUndefined)
    env.globals = dict(env.globals, url_for=lambda endpoint, **kw: '/action/' + endpoint,
                       role_is_readonly=lambda key: False)
    plan = [None] * 32
    plan[:4] = [323, 'Produkt', 400, 'w toku']
    stage = {'etap': mixing_stage, 'exists': True, 'is_running': True, 'czas_start': datetime(2026, 10, 11, 11)}
    with app.test_request_context('/'):
        html = env.get_template('dashboard/_dashboard_agro_stages.html').render(
            p=plan, linia='AGRO', sekcja='Zasyp', rola='masteradmin',
            etapy_sesje_mapa={323: [{'szarza_nr': 3, 'etapy': [stage], 'is_current': True, 'active_etap': mixing_stage}]},
            dosypki_oczekujace_mapa={('nr', 323, 3): 1, ('nr', 323, 1): 9},
            dosypki_mapa={323: [{'szarza_nr': 3, 'potwierdzono_dt': datetime(2026, 10, 11, 12)}]})
    import re
    button = re.search(r'<button[^>]*class="btn-action btn-stop"[^>]*>', html)
    assert button and 'disabled' not in button.group()
    assert 'STOP zablokowany: potwierdź dosypki' not in html
