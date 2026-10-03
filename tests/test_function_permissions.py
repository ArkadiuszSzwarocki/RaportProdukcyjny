import unittest
from unittest.mock import patch
from unittest.mock import MagicMock
import json
import tempfile
from pathlib import Path
from flask import Blueprint
from flask import Flask, session
from app.core.function_permissions import register_function_permissions, function_catalog


class FunctionPermissionsTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'test-only'
        self.app.add_url_rule('/action', endpoint='production.start_zlecenie', view_func=lambda: 'changed', methods=['POST'])
        self.app.add_url_rule('/read', endpoint='production.api_poll_zwolnienie', view_func=lambda: 'read')
        self.app.add_url_rule('/ack', endpoint='production.api_ack_zwolnienie', view_func=lambda: 'ack', methods=['POST'])
        # These tests isolate configurable function ACLs; resource guards have their own tests.
        self.resource_patch = patch('app.core.production_permissions.enforce_production_write', return_value=None)
        self.resource_patch.start()
        self.addCleanup(self.resource_patch.stop)
        register_function_permissions(self.app)
        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state.update(zalogowany=True, rola='pracownik')

    def test_explicit_deny_blocks_before_handler(self):
        with patch('app.core.function_permissions.configured_function_permission', return_value=False):
            self.assertEqual(self.client.post('/action').status_code, 403)


class RolesEditorTests(unittest.TestCase):
    def setUp(self):
        from app.blueprints.admin.roles import register_admin_roles_routes
        self.app = Flask(__name__)
        self.app.secret_key = 'test-only'
        bp = Blueprint('admin', __name__)
        register_admin_roles_routes(bp)
        self.app.register_blueprint(bp)
        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state.update(zalogowany=True, rola='masteradmin', login='test')

    def test_editor_exposes_namespaced_pages_and_function_rows(self):
        config = {'agro.zasyp': {'pracownik': {'access': True, 'readonly': False}}}
        connection = MagicMock()
        connection.cursor.return_value.fetchall.return_value = [('pracownik', 'Pracownik')]
        with patch('app.blueprints.admin.roles.get_db_connection', return_value=connection), patch(
            'app.blueprints.admin.roles._load_role_permissions', return_value=(config, 'test')), patch(
            'app.core.function_permissions.function_catalog', return_value={'function.production.start': {'label':'Rozpoczęcie'}}), patch(
            'app.blueprints.admin.roles.render_template', return_value='OK') as render:
            self.assertEqual(self.client.get('/admin/ustawienia/roles').status_code, 200)
            self.assertIn('agro.zasyp', render.call_args.kwargs['pages'])
            self.assertIn('function.production.start', render.call_args.kwargs['pages'])

    def test_save_roundtrip_preserves_unrepresented_roles(self):
        from app.blueprints.admin.roles import _project_config_path
        with tempfile.TemporaryDirectory() as folder:
            config_dir = Path(folder)/'config'
            config_dir.mkdir()
            config_path = config_dir/'role_permissions.json'
            config_path.write_text(json.dumps({'agro.zasyp': {
                'pracownik': {'access': True, 'readonly': False},
                'other': {'access': True, 'readonly': False}}}))
            payload = {'agro.zasyp': {'pracownik': {'access': False, 'readonly': False}}}
            with patch('app.blueprints.admin.roles._project_config_path', side_effect=lambda *parts: str(Path(folder).joinpath(*parts))), patch(
                'app.core.function_permissions.function_catalog', return_value={}), patch('app.blueprints.admin.roles.audit_log'):
                response = self.client.post('/admin/ustawienia/roles/save', json=payload)
                self.assertEqual(response.status_code, 200)
            saved = json.loads(config_path.read_text())
            self.assertFalse(saved['agro.zasyp']['pracownik']['access'])
            self.assertTrue(saved['agro.zasyp']['other']['access'])

class AdditionalFunctionPermissionsTests(FunctionPermissionsTests):
    def test_unconfigured_retains_existing_handler(self):
        with patch('app.core.function_permissions.configured_function_permission', return_value=None):
            self.assertEqual(self.client.post('/action').data, b'changed')

    def test_readonly_page_blocks_write(self):
        # Resource/page denial is authoritative even when the function itself is granted.
        with patch('app.core.function_permissions.configured_function_permission', return_value=True), patch(
            'app.core.production_permissions.enforce_production_write', return_value=('denied', 403)):
            self.assertEqual(self.client.post('/action', data={'sekcja':'Zasyp','linia':'AGRO'}).status_code, 403)

    def test_masteradmin_cannot_be_locked_out(self):
        with self.client.session_transaction() as state:
            state['rola'] = 'masteradmin'
        with patch('app.core.function_permissions.configured_function_permission', return_value=False):
            self.assertEqual(self.client.post('/action').status_code, 200)

    def test_catalog_includes_read_and_write(self):
        with self.app.app_context():
            catalog = function_catalog()
            self.assertTrue(catalog['function.production.start_zlecenie']['write'])
            self.assertNotIn('function.production.api_poll_zwolnienie', catalog)
            self.assertNotIn('function.production.api_ack_zwolnienie', catalog)

    def test_role_config_restricts_real_permission_evaluation(self):
        config = {'function.production.start_zlecenie': {'pracownik': {'access': False, 'readonly': False}}}
        with patch('app.core.contexts._get_role_permissions', return_value=config):
            self.assertEqual(self.client.post('/action').status_code, 403)

    def test_user_override_wins_over_role_allow(self):
        config = {'function.production.start_zlecenie': {'pracownik': {'access': True, 'readonly': False}}}
        deny = {'access': False, 'readonly': False}
        with self.client.session_transaction() as state:
            state['user_id'] = 17
        with patch('app.core.contexts._get_role_permissions', return_value=config), patch(
            'app.repositories.user_permission_override_repository.user_permission_override_repository.get_user_overrides',
            return_value={'function.production.start_zlecenie': deny}), patch(
            'app.repositories.user_permission_override_repository.user_permission_override_repository.get_user_override',
            return_value=deny):
            self.assertEqual(self.client.post('/action').status_code, 403)

    def test_override_storage_failure_denies_access(self):
        with self.client.session_transaction() as state:
            state['user_id'] = 17
        with patch('app.core.contexts._get_role_permissions', return_value={}), patch(
            'app.repositories.user_permission_override_repository.user_permission_override_repository.get_user_overrides',
            side_effect=RuntimeError('database unavailable')):
            self.assertEqual(self.client.post('/action').status_code, 403)

    def test_bulk_function_deny_leaves_polling_and_acknowledgements_working(self):
        with patch('app.core.function_permissions.configured_function_permission', return_value=False):
            self.assertEqual(self.client.post('/action').status_code, 403)
            self.assertEqual(self.client.get('/read').data, b'read')
            self.assertEqual(self.client.post('/ack', data={'sekcja':'Zasyp'}).data, b'ack')
