from unittest.mock import patch

import pytest
from flask import Blueprint, Flask

from app.blueprints.planning.lifecycle import register_planning_lifecycle_routes


@pytest.fixture
def resume_client():
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY='resume-response-test')
    app.add_url_rule('/', endpoint='main.index', view_func=lambda: 'dashboard')
    blueprint = Blueprint('planning', __name__, url_prefix='/api')
    register_planning_lifecycle_routes(blueprint, return_url_builder=lambda: '/')
    app.register_blueprint(blueprint)
    client = app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True, login='admin.test', rola='admin', grupa='ALL')
    return client


@pytest.mark.parametrize('success, code', [(True, 200), (False, 409)])
def test_ajax_resume_reports_actual_outcome(resume_client, success, code):
    message = 'Resumed' if success else 'Another order is active'
    with patch('app.blueprints.planning.lifecycle.PlanningStatusService.resume_plan', return_value=(success, message)) as resume:
        response = resume_client.post('/api/reanimate_zlecenie/123',
            data={'linia':'AGRO', 'sekcja':'Workowanie', 'data_planu':'2026-10-11'},
            headers={'X-Requested-With':'XMLHttpRequest'})
    assert response.status_code == code
    assert response.json['success'] is success
    assert response.json['message'] == message
    assert 'sekcja=Workowanie' in response.json['redirect_url']
    assert 'linia=AGRO' in response.json['redirect_url']
    resume.assert_called_once_with(123, linia='AGRO')


def test_non_ajax_resume_retains_redirect_and_warning(resume_client):
    with patch('app.blueprints.planning.lifecycle.PlanningStatusService.resume_plan', return_value=(False, 'Blocked')):
        response = resume_client.post('/api/reanimate_zlecenie/123', data={'linia':'AGRO','sekcja':'Workowanie'})
    assert response.status_code == 302
    with resume_client.session_transaction() as state:
        assert ('warning', 'Blocked') in state['_flashes']
