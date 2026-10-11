"""Laboratory navigation excludes the requested operational controls."""
# cspell:words Mixowanie
from datetime import date

import pytest
from jinja2 import ChainableUndefined


@pytest.mark.parametrize('role', ['laborant', 'laboratorium', 'masteradmin', 'operator'])
def test_sidebar_hides_operational_links_only_for_laboratory(app, role):
    env = app.jinja_env.overlay(undefined=ChainableUndefined)
    env.globals = dict(env.globals, url_for=lambda endpoint, **kw: '/action/' + endpoint,
                       role_has_access=lambda page: True)
    with app.test_request_context('/'):
        html = ''.join(env.get_template('includes/sidebar/' + template).render(
            role=role, effective_hall='ALL', app=app) for template in (
                '_sidebar_agro.html', '_sidebar_warehouse.html'))
    hidden = ['Podział Palety', 'Zużycie w Produkcji', 'Traceability', 'Zamówienia',
              'Dyspozycje Kompletacji', 'Załadunki / Wydania', 'Transfery na OSIP',
              'MAGAZYN OSIP', 'Przestoje AGRO', 'Raport Palet AGRO',
              'Maszyna LP01', 'Maszyny &amp; Telemetria', 'Historia Stacji']
    for label in hidden:
        if role in ('laborant', 'laboratorium'):
            assert label not in html
        elif role == 'masteradmin':
            assert label.replace('&amp;', '&') in html
    assert 'Zasyp Agro' in html
    if role != 'operator':
        assert 'Wszystkie Magazyny' in html
        assert 'Widok 3D Regałów' in html
        assert 'Mixowanie Palet' in html


@pytest.mark.parametrize('role', ['laborant', 'laboratorium', 'masteradmin'])
@pytest.mark.parametrize('section', ['Zasyp', 'Workowanie'])
def test_laboratory_header_and_quick_actions_hide_downtime_and_cleaning_bell(app, role, section):
    env = app.jinja_env.overlay(undefined=ChainableUndefined)
    env.globals = dict(env.globals, url_for=lambda endpoint, **kw: '/action/' + endpoint,
                       _=lambda text: text)
    with app.test_request_context('/'):
        html = env.get_template('includes/dashboard_top.html').render(
            rola=role, sekcja=section, linia='AGRO', dzisiaj=date(2026, 10, 11), plan=[],
            suma_plan=0, suma_wykonanie=0)
    assert ('/action/production.zglos_przestoj_page' in html) == (role == 'masteradmin')
    assert ('id="cleaningNotificationsBtn"' in html) == (role == 'masteradmin')
