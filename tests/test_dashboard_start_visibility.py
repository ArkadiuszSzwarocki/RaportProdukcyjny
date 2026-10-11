from datetime import date
from unittest.mock import Mock

import pytest
from jinja2 import ChainableUndefined

from app.services.planning.start_guard import get_unfinished_section_orders


@pytest.mark.parametrize('section,sections', [('Zasyp', ('Zasyp',)), ('Workowanie', ('Workowanie', 'Czyszczenie'))])
def test_dashboard_blockers_include_other_dates_and_share_start_guard(section, sections):
    cursor = Mock()
    cursor.fetchall.return_value = [(258, 'Produkt', 'wstrzymane')]
    assert get_unfinished_section_orders(cursor, 'plan_produkcji_agro', section) == cursor.fetchall.return_value
    sql, params = cursor.execute.call_args.args
    assert params == sections
    assert 'data_planu' not in sql
    assert "status IN ('w toku','zawieszone','wstrzymane')" in sql
    assert 'is_deleted' in sql
    assert 'FOR UPDATE' not in sql


@pytest.mark.parametrize('template', ['_dashboard_order_table_row.html', '_dashboard_order_card.html'])
@pytest.mark.parametrize('blocker_status', ['w toku', 'zawieszone', 'wstrzymane', None])
@pytest.mark.parametrize('order_status', ['zaplanowane', 'zawieszone'])
def test_start_hidden_for_unfinished_order_even_for_masteradmin(app, template, blocker_status, order_status):
    env = app.jinja_env.overlay(undefined=ChainableUndefined)
    env.globals = dict(env.globals, url_for=lambda endpoint, **kw: '/action/' + endpoint,
                       role_is_readonly=lambda scope: False)
    p = [None] * 32
    p[0:4] = [522, 'Produkt', 100, order_status]
    p[9] = 'AGRO'
    html = env.get_template('dashboard/' + template).render(
        p=p, rola='masteradmin', linia='AGRO', sekcja='Zasyp', order_index=1,
        unfinished_section_orders=[(258, 'Inny produkt', blocker_status)] if blocker_status else [],
        dzisiaj=date(2026, 10, 11), ns=env.globals['namespace'](is_active=False, active_plan_id=None),
    )
    assert ('/action/production.start_zlecenie' in html) == (blocker_status is None or order_status == 'zawieszone')


@pytest.mark.require_db
def test_dashboard_renders_new_controls_with_database_context(client):
    with client.session_transaction() as session:
        session.update(zalogowany=True, login='pytest', rola='masteradmin', grupa='ALL')
    response = client.get('/?sekcja=Zasyp&linia=AGRO&data=2026-10-11')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'cleaningNotificationsPanel' in html
    assert 'js/dashboard/popovers.js' in html
    assert 'aria-controls="dashboardActionsDropdownMenu"' in html
