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
