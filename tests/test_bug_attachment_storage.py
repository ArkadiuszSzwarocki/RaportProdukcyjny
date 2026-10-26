import base64
from pathlib import Path
from unittest.mock import patch
import pytest
from flask import Flask, Blueprint
from app.services.bug_attachment_service import BugAttachmentService

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jkXcAAAAASUVORK5CYII=')


@pytest.fixture
def app(tmp_path):
    from app.blueprints.admin.bugs import register_admin_bug_routes
    application=Flask(__name__,static_folder=str(tmp_path/'static'))
    application.secret_key='attachment-test'
    blueprint=Blueprint('admin',__name__)
    register_admin_bug_routes(blueprint,create_notification=lambda **kwargs:None)
    application.register_blueprint(blueprint)
    return application


def logged_client(app):
    client=app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True,login='operator',rola='masteradmin')
    return client


def test_shared_storage_and_legacy_fallback_serve_the_same_image_endpoint(app,tmp_path):
    shared=tmp_path/'shared'
    shared.mkdir()
    legacy=Path(app.static_folder)/'uploads'/'bugs'
    legacy.mkdir(parents=True)
    name='bug_123_0.png'
    (shared/name).write_bytes(PNG)
    (legacy/'bug_124_0.png').write_bytes(PNG)
    app.config['BUG_ATTACHMENTS_DIR']=str(shared)
    client=logged_client(app)
    for filename in [name,'bug_124_0.png']:
        response=client.get('/admin/zalaczniki/'+filename)
        assert response.status_code==200
        assert response.mimetype=='image/png'
        assert response.data==PNG
        response.close()


def test_missing_file_is_explicitly_unavailable_and_does_not_create_a_preview(app):
    with app.test_request_context():
        items=BugAttachmentService.items('["bug_123_0.png"]')
    assert items==[{'filename':'bug_123_0.png','available':False,'url':'/admin/zalaczniki/bug_123_0.png'}]
    assert logged_client(app).get(items[0]['url']).status_code==404


@pytest.mark.parametrize('raw',['not-json','"not-a-list"','{}',None])
def test_invalid_metadata_does_not_render_as_characters(app,raw):
    with app.test_request_context():
        assert BugAttachmentService.items(raw)==[]


@pytest.mark.parametrize('filename',['../outside.png','a/../outside.png','..\\outside.png','outside.txt','/outside.png'])
def test_resolver_rejects_paths_and_non_images(app,filename):
    with app.app_context():
        assert BugAttachmentService.resolve(filename) is None


def test_image_endpoint_requires_login(app):
    response=app.test_client().get('/admin/zalaczniki/bug_123_0.png')
    assert response.status_code in (302,401)


def test_bug_upload_directory_failure_is_not_reported_as_success(app,tmp_path):
    import io
    from app.blueprints.main.reporting import register_main_reporting_routes
    blueprint=Blueprint('main',__name__)
    register_main_reporting_routes(blueprint)
    app.register_blueprint(blueprint)
    client=logged_client(app)
    with patch('app.blueprints.main.reporting.os.makedirs',side_effect=PermissionError('read-only storage')), \
         patch('app.db.get_db_connection') as database:
        response=client.post('/api/zglos_blad_systemu',data={'opis':'Attachment test','zalaczniki':(io.BytesIO(PNG),'image.png')})
    assert response.status_code==500
    assert response.json['success'] is False
    database.assert_not_called()
