# cspell:words unrequested
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


def test_hall_roles_keep_worker_defaults_and_block_other_hall():
    from app.core.hall_roles import hall_for_role, with_hall_role_defaults, with_hall_roles
    from app.core.navigation_group_permissions import group_allowed
    from flask import session
    allow = {'access': True, 'readonly': False}
    deny = {'access': False, 'readonly': False}
    config = with_hall_role_defaults({
        'agro.zasyp': {'pracownik': allow},
        'psd.zasyp': {'pracownik': allow, 'psd': deny},
    })
    assert with_hall_roles([('pracownik', 'Pracownik')])[-2:] == [('agro', 'AGRO'), ('psd', 'PSD')]
    assert hall_for_role('agro', 'PSD') == 'AGRO'
    assert config['agro.zasyp']['agro'] == allow
    assert config['psd.zasyp']['psd'] == deny
    assert config['psd.zasyp']['agro'] == deny
    app = Flask(__name__)
    app.secret_key = 'hall-role-test'
    with app.test_request_context('/'), patch('app.core.contexts._get_role_permissions', return_value=config):
        session.update(zalogowany=True, rola='agro')
        assert group_allowed('agro')
        assert not group_allowed('psd')


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


def test_osip_group_deny_blocks_direct_routes_without_blocking_central_warehouse():
    from app.core.navigation_group_permissions import enforce_group_permission
    app = Flask(__name__)
    app.secret_key = 'group-test'
    app.before_request(enforce_group_permission)
    app.add_url_rule('/api/osip/inventory', endpoint='osip.inventory', view_func=lambda: 'osip')
    app.add_url_rule('/api/warehouse', endpoint='warehouse_v2.index', view_func=lambda: 'warehouse')
    config = {'group.osip': {'pracownik': {'access': True}, 'osip': {'access': False}}}
    repository = 'app.repositories.user_permission_override_repository.user_permission_override_repository'
    with app.test_client() as client, patch('app.core.contexts._get_role_permissions', return_value=config):
        with client.session_transaction() as state:
            state.update(zalogowany=True, rola='osip')
        assert client.get('/api/osip/inventory').status_code == 403
        assert client.get('/api/warehouse?zakladka=OSIP').status_code == 403
        assert client.get('/api/warehouse?linia=AGRO').status_code == 200
        with client.session_transaction() as state:
            state.update(rola='pracownik', user_id=99)
        with patch(repository + '.get_user_overrides', return_value={'group.osip': {'access': False}}):
            assert client.get('/api/osip/inventory').status_code == 403
        with patch(repository + '.get_user_overrides', return_value={}):
            assert client.get('/api/osip/inventory').status_code == 200


def test_agro_packaging_subgroup_and_individual_entries_are_enforced():
    from app.core.navigation_group_permissions import enforce_group_permission
    app = Flask(__name__)
    app.secret_key = 'subgroup-test'
    app.before_request(enforce_group_permission)
    app.add_url_rule('/api/lp01/items', endpoint='agro_warehouse.api_lp01_items', view_func=lambda: 'lp01')
    app.add_url_rule('/agro/api/opakowania', endpoint='agro_warehouse.api_packaging', view_func=lambda: 'packaging')
    app.add_url_rule('/warehouse-v2/historia-stacji/data', endpoint='warehouse_v2.station_history_data', view_func=lambda: 'history')
    config = {}
    with app.test_client() as client, patch('app.core.contexts._get_role_permissions', return_value=config):
        with client.session_transaction() as state:
            state.update(zalogowany=True, rola='pracownik', grupa='AGRO')
        config['group.agro_lp01'] = {'pracownik': {'access': False}}
        assert client.get('/api/lp01/items').status_code == 403
        assert client.get('/agro/api/opakowania').status_code == 200
        config['group.agro_packaging'] = {'pracownik': {'access': False}}
        assert client.get('/agro/api/opakowania').status_code == 403
        assert client.get('/warehouse-v2/historia-stacji/data').status_code == 200
        config['group.agro_station_history'] = {'pracownik': {'access': False}}
        assert client.get('/warehouse-v2/historia-stacji/data', json={}).status_code == 403


def test_warehouse_entry_switch_blocks_split_without_blocking_regular_scanner_move():
    from app.core.navigation_group_permissions import enforce_group_permission
    app = Flask(__name__)
    app.secret_key = 'warehouse-entry-test'
    app.before_request(enforce_group_permission)
    app.add_url_rule('/agro/scanner/move', endpoint='scanner.move', view_func=lambda: 'moved', methods=['POST'])
    app.add_url_rule('/magazyn-dostawy/api/podzial-palety', endpoint='magazyn_dostawy.api_podzial_palety',
                     view_func=lambda: 'split', methods=['POST'])
    config = {'group.entry_split': {'pracownik': {'access': False}}}
    with app.test_client() as client, patch('app.core.contexts._get_role_permissions', return_value=config):
        with client.session_transaction() as state:
            state.update(zalogowany=True, rola='pracownik')
        assert client.post('/magazyn-dostawy/api/podzial-palety', json={'linia': 'OSIP'}).status_code == 403
        assert client.post('/agro/scanner/move', json={'amount_to_move': 1}).status_code == 403
        assert client.post('/agro/scanner/move', json={'amount_to_move': None}).status_code == 200


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
