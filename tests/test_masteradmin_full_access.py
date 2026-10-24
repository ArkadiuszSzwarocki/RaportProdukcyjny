"""MasterAdmin bypasses role ACLs without bypassing resource integrity."""
from unittest.mock import patch
from flask import Flask, session
import pytest
from app.core.contexts import inject_role_permissions
from app.core.function_permissions import configured_function_permission
from app.decorators import dynamic_role_required, admin_required, masteradmin_required, zarzad_required


@pytest.mark.parametrize('role',['masteradmin','MasterAdmin','master admin','master_admin','master-admin'])
def test_masteradmin_has_every_catalog_page_and_no_readonly(role):
    app=Flask(__name__);app.secret_key='tests'
    with app.test_request_context('/warehouse-v2/?linia=OSIP',method='POST'):
        session.update(zalogowany=True,rola=role,grupa='OSIP',user_id=123)
        with patch('app.core.contexts._get_role_permissions',return_value={'restricted':{'masteradmin':{'access':False,'readonly':True}}}):
            helpers=inject_role_permissions()
            for page in ['restricted','psd.zasyp','agro.workowanie','osip.magazyn','ustawienia.users','function.warehouse_v2.update_weight','new.unconfigured.page']:
                assert helpers['role_has_access'](page)
                assert not helpers['role_is_readonly'](page)
            assert configured_function_permission() is True


@pytest.mark.parametrize('decorator',[dynamic_role_required('denied'),admin_required,masteradmin_required,zarzad_required])
def test_privileged_decorators_accept_normalized_masteradmin(decorator):
    app=Flask(__name__);app.secret_key='tests'
    app.add_url_rule('/test',view_func=decorator(lambda:'OK'),methods=['POST'])
    with app.test_client() as client:
        with client.session_transaction() as state:state.update(zalogowany=True,rola='master-admin')
        with patch('app.core.contexts.inject_role_permissions',side_effect=AssertionError('MasterAdmin must not need ACL lookup')):
            assert client.post('/test').status_code==200


def test_anonymous_session_cannot_use_masteradmin_name():
    app=Flask(__name__);app.secret_key='tests'
    app.add_url_rule('/test',view_func=masteradmin_required(lambda:'OK'))
    with app.test_client() as client:
        with client.session_transaction() as state:state['rola']='masteradmin'
        assert client.get('/test',headers={'Accept':'application/json'}).status_code==401


@pytest.mark.parametrize('role,expected',[('masteradmin',200),('pracownik',403)])
def test_hours_correction_for_other_employee(role,expected):
    from unittest.mock import MagicMock
    from app.blueprints.schedule.base import edytuj_godziny
    app=Flask(__name__);app.secret_key='tests'
    connection=MagicMock();connection.cursor.return_value.fetchone.return_value=(1,)
    with app.test_request_context('/edytuj_godziny',method='POST',data={'pracownik_id':'99','date':'2026-10-23','godziny':'8'}):
        session.update(zalogowany=True,rola=role,pracownik_id=1)
        with patch('app.blueprints.schedule.base.get_db_connection',return_value=connection) as db:
            response=app.make_response(edytuj_godziny())
            assert response.status_code==expected
            if expected==200:connection.commit.assert_called_once()
            else:db.assert_not_called()


def test_masteradmin_can_reopen_mom():
    from app.blueprints.mom.base import api_reopen,MomService
    app=Flask(__name__);app.secret_key='tests'
    with app.test_request_context('/agro/api/mom/7/reopen',method='POST'):
        session.update(zalogowany=True,rola='masteradmin')
        with patch.object(MomService,'reopen_mom') as reopen:
            assert app.make_response(api_reopen(7)).status_code==200
            reopen.assert_called_once_with(7)


def test_warehouse_version_changes_even_with_future_dated_assets(tmp_path):
    from app.core.contexts import _compute_warehouse_ui_version
    import os
    js = tmp_path / 'static/js/warehouse_v2'
    templates = tmp_path / 'templates/warehouse_v2/modals'
    js.mkdir(parents=True)
    templates.mkdir(parents=True)
    (js / 'state.js').write_text('old asset')
    os.utime(js / 'state.js', (2000000000, 2000000000))
    modal = js / 'modals.js'
    modal.write_text('old permissions')
    markup = templates / '_modal_pallet_details.html'
    markup.write_text('old markup')
    app = Flask(__name__, root_path=str(tmp_path))
    with app.app_context():
        before = _compute_warehouse_ui_version()
        modal.write_text('new permissions')
        after_script = _compute_warehouse_ui_version()
        assert after_script != before
        markup.write_text('new markup')
        assert _compute_warehouse_ui_version() != after_script


@pytest.mark.parametrize('role', ['masteradmin', 'master admin', 'master_admin', 'master-admin'])
def test_real_pallet_template_uses_server_master_permissions(role):
    from pathlib import Path
    from flask import render_template
    root = Path(__file__).resolve().parents[1]
    app = Flask(__name__, template_folder=str(root / 'templates'))
    app.secret_key = 'tests'
    app.context_processor(inject_role_permissions)
    with app.test_request_context('/'):
        session.update(zalogowany=True, rola=role)
        html = render_template('warehouse_v2/modals/_modal_pallet_details.html', printers=[])
        assert 'data-masteradmin="true"' in html
        for button in ['btnMoveLocation', 'btnUpdateWeight', 'btnRename', 'toggleBlockBtn', 'btnArchive', 'adminDeleteContainer']:
            assert f'id="{button}"' in html
        assert 'MasterAdmin ma dostęp do wszystkich operacji' in html
