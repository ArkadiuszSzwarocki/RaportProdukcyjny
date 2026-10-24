"""Permission descriptions do not alter the saved ACL keys or authorization."""
import json
from unittest.mock import MagicMock, patch
from flask import Flask
from app.core.permission_presentation import permission_metadata
from app.blueprints.admin.user_permissions import register_user_permissions_routes
from flask import Blueprint

SHARED = 'function.production.potwierdz_dosypke'
AGRO = 'function.production.agro_folio_add_roll'
FUNCTIONS = {SHARED:{'label':'Potwierdzenie dosypki'}, AGRO:{'label':'Podpięcie rolki folii'}}


def test_shared_and_hall_specific_actions_have_correct_groups():
    shared = permission_metadata(SHARED, FUNCTIONS)
    assert shared['label'] == 'Potwierdzenie dosypki'
    assert {group['id'] for group in shared['groups']} == {'agro.zasyp','psd.zasyp'}
    assert [group['id'] for group in permission_metadata(AGRO,FUNCTIONS)['groups']] == ['agro.workowanie']


def test_pages_are_named_in_their_production_context():
    page = permission_metadata('agro.zasyp', FUNCTIONS)
    assert page['label'] == 'Dostęp do strony'
    assert page['groups'] == [{'id':'agro.zasyp','title':'AGRO · Zasyp'}]


def make_app(tmp_path):
    (tmp_path/'config').mkdir()
    (tmp_path/'config/role_permissions.json').write_text(json.dumps({
        'agro.zasyp':{'laborant':{'access':False,'readonly':False}},
        AGRO:{'laborant':{'access':True,'readonly':False}},
    }))
    app=Flask(__name__,root_path=str(tmp_path));app.secret_key='test'
    blueprint=Blueprint('permissions_test',__name__)
    register_user_permissions_routes(blueprint);app.register_blueprint(blueprint)
    app.extensions['function_permission_catalog']=FUNCTIONS
    return app


def test_api_distinguishes_role_rule_from_operation_policy_and_keeps_overrides(tmp_path):
    app=make_app(tmp_path)
    conn=MagicMock();conn.cursor.return_value.fetchone.return_value={'id':99,'login':'test_laborant','rola':'laborant'}
    with app.test_client() as client, patch('app.blueprints.admin.user_permissions.get_db_connection',return_value=conn), patch('app.blueprints.admin.user_permissions.user_permission_override_repository.get_user_overrides',return_value={SHARED:{'access':False,'readonly':False}}):
        with client.session_transaction() as state:state.update(zalogowany=True,rola='masteradmin',login='test')
        data=client.get('/admin/api/user/99/permissions').get_json()
    modules={row['page_key']:row for row in data['modules']}
    assert modules[SHARED]['default_source']=='operation_policy'
    assert modules[SHARED]['has_override'] and not modules[SHARED]['effective_access']
    assert modules[AGRO]['default_source']=='role'
    assert not modules['agro.zasyp']['role_access']
    conn.commit.assert_not_called()


def test_editor_api_remains_masteradmin_only(tmp_path):
    app=make_app(tmp_path)
    with app.test_client() as client:
        assert client.get('/admin/api/user/99/permissions',headers={'Accept':'application/json'}).status_code==401
        with client.session_transaction() as state:state.update(zalogowany=True,rola='admin')
        assert client.get('/admin/api/user/99/permissions',headers={'Accept':'application/json'}).status_code==403


def test_save_still_uses_one_original_key_and_no_unrequested_changes(tmp_path):
    app=make_app(tmp_path)
    conn=MagicMock();conn.cursor.return_value.fetchone.return_value={'login':'test_laborant'}
    with app.test_client() as client, patch('app.blueprints.admin.user_permissions.get_db_connection',return_value=conn), patch('app.blueprints.admin.user_permissions.user_permission_override_repository') as repository:
        repository.set_user_override.return_value=True
        with client.session_transaction() as state:state.update(zalogowany=True,rola='masteradmin',login='test')
        response=client.post('/admin/api/user/99/permissions',json={'overrides':{SHARED:{'mode':'deny','readonly':False}}})
        assert response.status_code==200
        repository.set_user_override.assert_called_once_with(99,SHARED,False,False)
        repository.delete_user_override.assert_not_called()
