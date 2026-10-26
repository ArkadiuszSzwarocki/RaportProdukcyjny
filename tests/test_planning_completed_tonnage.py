from unittest.mock import Mock

import pytest

from app.services.planning.commands.edytuj_plan_command import EdytujPlanCommand


@pytest.mark.parametrize('line', ['AGRO', 'PSD'])
def test_completed_plan_tonnage_cannot_be_changed(line):
    connection = Mock()
    cursor = Mock()
    cursor.fetchone.return_value = (12, 'Finished', 100, 'Workowanie', '2026-10-11',
                                   'zakonczone', '', '', None, '', None, None, None, None, '')
    success, message, changes, status = EdytujPlanCommand.execute(
        connection, cursor, line, 12, {'tonaz': 200}, {'rola': 'admin'})
    assert success is False
    assert status == 403
    assert changes == {}
    assert 'zakończonego' in message
    cursor.execute.assert_called_once()
    assert 'FOR UPDATE' in cursor.execute.call_args.args[0]
    assert not connection.commit.called


@pytest.mark.parametrize('line', ['AGRO', 'PSD'])
@pytest.mark.parametrize('state', ['w toku', 'zawieszone'])
@pytest.mark.parametrize('role', ['masteradmin', 'planista'])
def test_started_plan_allows_only_tonnage(line, state, role):
    from flask import Flask
    from unittest.mock import patch
    cursor = Mock()
    cursor.fetchone.return_value = (12, 'Started', 100, 'Workowanie', '2026-10-25',
                                   state, '', '', None, '', None, 1, 2, None, '')
    with Flask(__name__).app_context(), patch('app.services.planning.commands.edytuj_plan_command.log_plan_history'):
        result = EdytujPlanCommand.execute(Mock(), cursor, line, 12, {'produkt': 'Changed'}, {'rola': role})
        assert result[0] is False and result[3] == 403
        assert not any(call.args[0].startswith('UPDATE') for call in cursor.execute.call_args_list)
        result = EdytujPlanCommand.execute(Mock(), cursor, line, 12, {'tonaz': 200}, {'rola': role})
        assert result[0] is True and result[2] == {'tonaz': {'before': 100, 'after': 200}}


@pytest.mark.parametrize('field,value', [('produkt', 'Changed'), ('data_planu', '2026-10-26'), ('opakowanie_id', 3), ('etykieta_id', 4), ('rodzaj_palety', 'eksportowa')])
def test_planned_zasyp_is_locked_when_linked_workowanie_is_suspended(field, value):
    from flask import Flask
    cursor = Mock()
    cursor.fetchone.return_value = (321, 'testowe 45', 100, 'Zasyp', '2026-10-25',
                                   'zaplanowane', '', '', None, '', None, 1, 2, None, '')
    cursor.fetchall.return_value = [('zawieszone',)]
    with Flask(__name__).app_context():
        result = EdytujPlanCommand.execute(Mock(), cursor, 'AGRO', 321, {field: value}, {'rola': 'masteradmin'})
    assert result[0] is False and result[3] == 403
    assert not any(call.args[0].startswith('UPDATE') for call in cursor.execute.call_args_list)


def test_planned_zasyp_tonnage_can_change_when_linked_workowanie_is_suspended():
    from flask import Flask
    from unittest.mock import patch
    cursor = Mock()
    cursor.fetchone.return_value = (321, 'testowe 45', 100, 'Zasyp', '2026-10-25',
                                   'zaplanowane', '', '', None, '', None, 1, 2, None, '')
    cursor.fetchall.return_value = [('zawieszone',)]
    with Flask(__name__).app_context(), patch('app.services.planning.commands.edytuj_plan_command.log_plan_history'):
        result = EdytujPlanCommand.execute(Mock(), cursor, 'AGRO', 321, {'tonaz': 200}, {'rola': 'masteradmin'})
    assert result[0] is True
    assert list(result[2]) == ['tonaz']


def test_agro_planner_uses_linked_stage_status_and_keeps_same_product_orders_separate():
    from app.blueprints.planista.panel_data import load_agro_plan_rows
    cursor = Mock()
    cursor.fetchall.return_value = [
        {'id': 321, 'zasyp_id': None, 'produkt': 'Same product', 'sekcja': 'Zasyp', 'status': 'zaplanowane'},
        {'id': 323, 'zasyp_id': None, 'produkt': 'Same product', 'sekcja': 'Zasyp', 'status': 'zaplanowane'},
        {'id': 322, 'zasyp_id': 321, 'produkt': 'Same product', 'sekcja': 'Workowanie', 'status': 'zawieszone'},
        {'id': 324, 'zasyp_id': 323, 'produkt': 'Same product', 'sekcja': 'Workowanie', 'status': 'zaplanowane'},
    ]
    rows = load_agro_plan_rows(cursor, '2026-10-25')
    assert [(row['id'], row['status']) for row in rows] == [(321, 'zawieszone'), (323, 'zaplanowane')]



def test_drag_reorder_cannot_move_planned_parent_with_started_stage():
    from flask import Flask
    from unittest.mock import patch
    from app.services.plan_movement_service import PlanMovementService
    connection = Mock()
    cursor = connection.cursor.return_value
    cursor.fetchall.return_value = [(321, 1, 'zaplanowane')]
    with Flask(__name__).app_context(), patch('app.services.plan_movement_service.get_db_connection', return_value=connection):
        success, message = PlanMovementService.reorder_plans('Zasyp', '2026-10-25', [323, 321], linia='AGRO')
    assert success is False
    connection.commit.assert_not_called()
    assert not any(call.args[0].startswith('UPDATE') for call in cursor.execute.call_args_list)
