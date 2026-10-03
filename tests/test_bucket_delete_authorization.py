from flask import Flask
from unittest.mock import patch
import pytest
from app.blueprints.maluchy.blueprint import maluchy_bp
import app.blueprints.maluchy.api  # Register the real handlers.


@pytest.fixture
def bucket_client():
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY='test')
    app.register_blueprint(maluchy_bp, url_prefix='/maluchy')
    client = app.test_client()
    with client.session_transaction() as session:
        session['zalogowany'] = True
        session['rola'] = 'pracownik'
        session['grupa'] = 'PSD'
    return client


def test_actual_bucket_hall_controls_permission(bucket_client):
    with patch('app.repositories.bucket_maluch_repository.BucketMaluchRepository.find_by_id', return_value={'linia': 'AGRO'}), patch(
            'app.services.bucket_maluch_service.BucketMaluchService.delete_bucket') as delete:
        response = bucket_client.post('/maluchy/api/delete', json={'bucket_id': 1, 'linia': 'PSD'})
    assert response.status_code == 403
    delete.assert_not_called()


@pytest.mark.parametrize('force,expected', [('false', False), ('0', False), ('true', True)])
def test_form_force_is_parsed_explicitly(bucket_client, force, expected):
    with patch('app.repositories.bucket_maluch_repository.BucketMaluchRepository.find_by_id', return_value={'linia': 'PSD'}), patch(
            'app.core.production_permissions._page_allowed', return_value=True), patch(
            'app.services.bucket_maluch_service.BucketMaluchService.delete_bucket', return_value=(True, 'OK')) as delete:
        response = bucket_client.post('/maluchy/api/delete', data={'bucket_id': 1, 'force': force})
    assert response.status_code == 200
    assert delete.call_args.kwargs['force'] is expected


def test_readonly_permission_prevents_delete(bucket_client):
    with patch('app.repositories.bucket_maluch_repository.BucketMaluchRepository.find_by_id', return_value={'linia': 'PSD'}), patch(
            'app.core.production_permissions._page_allowed', return_value=False) as permission, patch(
            'app.services.bucket_maluch_service.BucketMaluchService.delete_bucket') as delete:
        response = bucket_client.post('/maluchy/api/delete', json={'bucket_id': 1})
    assert response.status_code == 403
    permission.assert_called_once_with('PSD', 'zasyp', write=True)
    delete.assert_not_called()
