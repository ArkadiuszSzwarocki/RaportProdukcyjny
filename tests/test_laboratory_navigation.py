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
                '_sidebar_agro.html', '_sidebar_warehouse.html', '_sidebar_settlements.html'))
    hidden = ['Podział Palety', 'Zużycie w Produkcji', 'Traceability', 'Zamówienia',
              'Dyspozycje Kompletacji', 'Załadunki / Wydania', 'Transfery na OSIP',
              'MAGAZYN OSIP', 'Historia Stacji', 'Mixowanie Palet']
    for label in hidden:
        if role in ('laborant', 'laboratorium'):
            assert label not in html
        elif role == 'masteradmin':
            assert label.replace('&amp;', '&') in html
    assert 'Zasyp Agro' in html
    if role != 'operator':
        assert 'Wszystkie Magazyny' in html
        assert 'Widok 3D Regałów' not in html
        assert 'Stanowisko LP01' in html
    # These shortcuts were consolidated into their dedicated sidebar sections.
    assert 'Maszyna LP01' not in html
    if role == 'masteradmin':
        assert 'Raport Palet AGRO' not in html
        assert 'Maszyny & Telemetria' not in html


@pytest.mark.parametrize('role', ['laborant', 'laboratorium', 'masteradmin'])
@pytest.mark.parametrize('section', ['Zasyp', 'Workowanie'])
@pytest.mark.parametrize('running', [False, True])
def test_laboratory_header_and_quick_actions_hide_downtime_and_cleaning_bell(app, role, section, running):
    env = app.jinja_env.overlay(undefined=ChainableUndefined)
    env.globals = dict(env.globals, url_for=lambda endpoint, **kw: '/action/' + endpoint,
                       _=lambda text: text)
    with app.test_request_context('/'):
        html = env.get_template('includes/dashboard_top.html').render(
            rola=role, sekcja=section, linia='AGRO', dzisiaj=date(2026, 10, 11), plan=[(323, 'Produkt', 400, 'w toku' if running else 'zaplanowane', None, None, None, 0)],
            suma_plan=0, suma_wykonanie=0)
    assert ('/action/production.zglos_przestoj_page' in html) == (role == 'masteradmin' and running)
    assert ('id="cleaningNotificationsBtn"' in html) == (role == 'masteradmin' and running and section == 'Zasyp')


@pytest.mark.parametrize('role', ['laborant', 'laboratorium', 'masteradmin'])
def test_laboratory_quick_actions_keep_recipe_date_and_focus_without_marked_actions(app, role):
    env = app.jinja_env.overlay(undefined=ChainableUndefined)
    env.globals = dict(env.globals, url_for=lambda endpoint, **kw: '/action/' + endpoint,
                       _=lambda text: text)
    with app.test_request_context('/'):
        html = env.get_template('dashboard/_dashboard_actions_dropdown.html').render(
            rola=role, sekcja='Zasyp', linia='AGRO', dzisiaj=date(2026, 10, 11),
            plan=[(323, 'Produkt', 400, 'w toku')], agro_focus_mode=True, production_toolbar_visible=True,
            kgph_stats_mapa={323: {'real_work': 346.7, 'timeline': 346.7}})
    # Only inspect rendered controls, not the shared JavaScript helpers below them.
    controls = html.split('<script>')[0]
    for label in ('Rejestr Przestojów', 'Wydajność', 'Surowce w produkcji',
                  'Kalkulator Zapotrzebowania', 'Zgłoś czyszczenie magnesu',
                  'Zgłoś czyszczenie separatora'):
        assert (label in controls) == (role == 'masteradmin')
    for label in ('Receptura / Składniki', 'current-date-iso', 'Pokaż ukryte zlecenia'):
        assert label in controls
