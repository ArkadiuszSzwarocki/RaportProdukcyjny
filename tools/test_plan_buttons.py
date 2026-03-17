import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app.core.factory import create_app
from flask import session

app = create_app(init_db=False)

with app.test_request_context('/planista'):
    # Simulate logged-in admin
    session['rola'] = 'admin'
    # Provide simple translation function used in templates
    app.jinja_env.globals['_'] = lambda s: s
    # Provide simplified role_has_access used in layout/context processors
    app.jinja_env.globals['role_has_access'] = lambda key: True

    # Build a plany_list with one Zasyp finished but wykonanie < plan
    # Indices per planista.py: [id, sekcja, produkt, tonaz, status, kolejnosc, real_start, real_stop, tonaz_rzeczywisty, typ_produkcji, wyjasnienie, uszkodzone_worki, czas_trwania]
    p = [9999, 'Zasyp', 'TEST PRODUCT', 1000.0, 'zakonczone', 1, None, None, 800.0, 'worki_zgrzewane_20', '', 0]
    plany = [p]

    # Minimal context required by template
    context = {
        'plany': plany,
        'wybrana_data': '2026-03-16',
        'palety_mapa': {},
        'suma_plan': 1000,
        'suma_wyk': 800,
        'procent': 80,
        'suma_minut_plan': 60,
        'procent_czasu': 13,
        'quality_count': 0,
        'quality_orders': [],
        'rozliczenia': [],
        'current_role': 'admin',
        'aktywna_zakladka': 'psd',
        'plany_agro': [],
        'suma_plan_agro': 0,
        'suma_wyk_agro': 0,
        'suma_minut_plan_agro': 0,
        'procent_agro': 0,
        'has_incomplete_plans': True
    }

    tpl = app.jinja_env.get_template('planista.html')
    rendered = tpl.render(**context)

    found_badge = 'Niezrealizowane' in rendered
    found_button = '📦➡️' in rendered or 'Przenieś niezrealizowane' in rendered or 'btn-warning' in rendered

    print('FOUND_BADGE:', found_badge)
    print('FOUND_BUTTON:', found_button)
    # Optionally save to file for manual inspection
    with open('test_planista_render.html', 'w', encoding='utf-8') as f:
        f.write(rendered)
    print('Rendered template saved to test_planista_render.html')
