from unittest.mock import patch
import pytest

@pytest.mark.parametrize('role,allowed',[('lider',True),('zarzad',True),('masteradmin',True),('pracownik',False),('magazynier',False)])
def test_delete_attendance_permissions(app,role,allowed):
    from app.blueprints.leaves.base import usun_obecnosc
    from flask import session
    with app.test_request_context('/api/usun_obecnosc/1056',method='POST',headers={'X-Requested-With':'XMLHttpRequest'}):
        session.update(zalogowany=True,rola=role,login='test')
        with patch('app.blueprints.leaves.base.AttendanceService.delete_absence_record',return_value=True) as delete:
            response=usun_obecnosc(1056)
        if allowed:
            delete.assert_called_once_with(1056)
            assert response.get_json()['success'] is True
        else:
            delete.assert_not_called()
            assert response[1]==403
