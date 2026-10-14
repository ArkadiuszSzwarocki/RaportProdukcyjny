from unittest.mock import MagicMock, patch

import pytest

from app.services.planning.start_guard import guard_section_start
from app.services.planning.status import PlanningStatusService


@pytest.mark.parametrize('target_status', ['zawieszone', 'wstrzymane'])
@pytest.mark.parametrize('other_status', ['zawieszone', 'wstrzymane', 'w toku'])
def test_resume_skips_other_paused_orders_but_never_a_running_order(target_status, other_status):
    cursor = MagicMock()
    cursor.fetchall.return_value = [(258, 'AGRO MILK TOP', other_status), (323, 'Czyszczenie', target_status)]
    result = guard_section_start(cursor, 'plan_produkcji_agro', 323, 'Zasyp')
    assert (result is None) == (other_status != 'w toku')
    assert 'FOR UPDATE' in cursor.execute.call_args.args[0]
    if other_status == 'w toku':
        assert 'Najpierw wstrzymaj albo zakończ' in result


def test_new_start_stays_blocked_when_other_orders_are_paused():
    cursor = MagicMock()
    cursor.fetchall.return_value = [(258, 'AGRO MILK TOP', 'wstrzymane'), (323, 'Czyszczenie', 'zawieszone')]
    assert guard_section_start(cursor, 'plan_produkcji_agro', 522, 'Zasyp') is not None


@pytest.mark.parametrize('other_status', ['wstrzymane', 'w toku'])
def test_resume_status_service_commits_only_when_no_other_order_runs(app, other_status):
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchone.return_value = ('Zasyp', 'Czyszczenie', 'zawieszone')
    cursor.fetchall.return_value = [(258, 'AGRO MILK TOP', other_status), (323, 'Czyszczenie', 'zawieszone')]
    with app.test_request_context('/resume'), patch('app.services.planning.status.get_db_connection', return_value=connection):
        ok, message = PlanningStatusService.resume_plan(323, 'AGRO')
    assert ok == (other_status != 'w toku')
    updates = [call.args for call in cursor.execute.call_args_list if call.args[0].startswith('UPDATE')]
    if ok:
        connection.commit.assert_called_once()
        assert any("SET status='w toku'" in sql and params == (323,) for sql, params in updates)
    else:
        connection.commit.assert_not_called()
        assert updates == []
    connection.close.assert_called_once()
