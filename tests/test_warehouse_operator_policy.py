"""Employee warehouse access is global; sensitive stock corrections remain restricted."""
from unittest.mock import MagicMock, patch
from contextlib import ExitStack
import pytest
from flask import Flask, session
from app.core.production_permissions import _page_allowed
from app.core.contexts import inject_role_permissions
from app.blueprints.agro_warehouse import agro_warehouse_bp
from app.blueprints.magazyn_dostawy import magazyn_dostawy_bp
from app.blueprints.warehouse import warehouse_bp
from app.blueprints.warehouse_v2 import warehouse_v2_bp
from app.core.function_permissions import register_function_permissions
from app.services.lp01_service import Lp01Service
from app.services.production_consumption_service import ProductionConsumptionService


@pytest.fixture
def app():
    instance = Flask(__name__)
    instance.secret_key = 'operator-policy-test'
    instance.register_blueprint(agro_warehouse_bp)
    instance.register_blueprint(magazyn_dostawy_bp)
    instance.register_blueprint(warehouse_bp)
    instance.register_blueprint(warehouse_v2_bp)
    register_function_permissions(instance)
    return instance


@pytest.mark.parametrize('role', ['operator', 'pracownik', 'magazynier'])
@pytest.mark.parametrize('group', ['PSD', 'AGRO', 'OSIP'])
def test_global_stock_access_does_not_grant_other_hall_production(app, role, group):
    with app.test_request_context('/'):
        session.update(zalogowany=True, rola=role, grupa=group)
        for line in ['PSD', 'AGRO', 'OSIP', 'ALL']:
            assert _page_allowed(line, 'magazyn')
        other = 'PSD' if group != 'PSD' else 'AGRO'
        assert not _page_allowed(other, 'zasyp')
        helpers = inject_role_permissions()
        assert helpers['role_has_access']('magazyn.view')
        assert helpers['role_has_access']('magazyn.agro_packaging')
        assert not helpers['role_has_access']('magazyn.inventory') if role != 'magazynier' else True


@pytest.mark.parametrize('role', ['operator', 'pracownik', 'magazynier', 'lider', 'zarzad', 'admin', 'masteradmin'])
@pytest.mark.parametrize('operation', ['dispatch', 'return', 'archive'])
def test_every_employee_can_use_lp01_panel_across_halls(app, role, operation):
    client = app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True, rola=role, grupa='PSD', login='policy-test')
    service = 'app.services.lp01_service.Lp01Service.archive_lp01_item' if operation == 'archive' else 'app.services.warehouse_v2_service.WarehouseV2Service.move_pallet'
    with patch(service, return_value=(True, 'OK')) as action:
        response = client.post('/api/lp01/' + operation, json={
            'id': 7, 'type': 'Opakowanie', 'linia': 'AGRO', 'location': 'R010101'})
    assert response.status_code == 200
    assert response.json['success']
    action.assert_called_once()


@pytest.mark.parametrize('role', ['operator', 'pracownik', 'magazynier'])
def test_every_employee_can_start_bb_mz_return(app, role):
    client = app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True, rola=role, grupa='PSD', login='policy-test')
    with patch('app.services.agro.agro_tanks_service.AgroTanksService.return_from_production', return_value=(True, 99, 'RETURN99')) as action, patch(
            'app.services.scanner_service.ScannerService.get_label_data', return_value=None), patch(
            'app.services.print_server.get_printer'):
        response = client.post('/agro/api/return', json={
            'surowiec_id': 7, 'ilosc': 10, 'ruch_produkcja_id': 88, 'linia': 'AGRO'})
    assert response.status_code == 200
    assert response.json['success']
    action.assert_called_once()


@pytest.mark.parametrize('role,allowed', [('operator', False), ('pracownik', False), ('magazynier', False), ('laborant', False), ('admin', True), ('masteradmin', True), ('zarzad', True), ('lider', True)])
@pytest.mark.parametrize('operation', ['add', 'delete'])
def test_only_requested_roles_can_change_location_dictionary(app, role, allowed, operation):
    client = app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True, rola=role, grupa='PSD', login='policy-test')
    method = 'add_allowed_location' if operation == 'add' else 'delete_allowed_location'
    with patch('app.repositories.settings_repository.SettingsRepository.' + method, return_value=(True, 'OK')) as action:
        if operation == 'add':
            response = client.post('/magazyn-dostawy/api/ustawienia_lokalizacji', json={'nazwa': 'R01'})
        else:
            response = client.delete('/magazyn-dostawy/api/ustawienia_lokalizacji/7', headers={'Accept': 'application/json'})
    assert response.status_code == (200 if allowed else 403)
    assert action.called == allowed


def test_legacy_weighing_endpoint_is_removed(app):
    assert not any('wazenie_magazyn' in rule.rule for rule in app.url_map.iter_rules())
    assert app.test_client().post('/wazenie_magazyn/7').status_code == 404


@pytest.mark.parametrize('location', ['MP01', 'MS01', 'R010101', '', 'OCZEKUJACE'])
def test_consumption_cannot_zero_warehouse_stock(app, location):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = {'id': 7, 'nr_palety': 'TEST7', 'lokalizacja': location, 'stan_magazynowy': 100}
    with app.test_request_context('/'):
        session.update(zalogowany=True, rola='pracownik', grupa='PSD')
        with patch('app.services.production_consumption_service.get_db_connection', return_value=conn):
            result = ProductionConsumptionService.consume_and_archive_pallet(7, 'Opakowanie', 'AGRO')
    assert not result[0]
    conn.commit.assert_not_called()
    assert not any(call.args[0].strip().startswith(('INSERT', 'UPDATE', 'DELETE')) for call in conn.cursor.return_value.execute.call_args_list)


@pytest.mark.parametrize('location', ['R010101', 'MP01', 'BB03'])
def test_lp01_cannot_consume_stock_outside_machine(app, location):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = {'id': 7, 'nr_palety': 'TEST7', 'lokalizacja': location, 'stan_magazynowy': 100}
    with patch('app.services.lp01_service.get_db_connection', return_value=conn):
        result = Lp01Service.archive_lp01_item(7)
    assert not result[0]
    conn.commit.assert_not_called()


@pytest.mark.parametrize('amount', [float('nan'), float('inf'), -1, 101])
def test_lp01_consumption_rejects_invalid_quantity(app, amount):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = {'id': 7, 'nr_palety': 'TEST7', 'lokalizacja': 'LP01', 'stan_magazynowy': 100}
    with patch('app.services.lp01_service.get_db_connection', return_value=conn), patch(
            'app.services.magazyn_dostawy.commands.pallet_lock_manager.PalletLockManager.has_quality_or_manual_block', return_value=False):
        result = Lp01Service.archive_lp01_item(7, consumed_qty=amount)
    assert not result[0]
    conn.commit.assert_not_called()


@pytest.mark.parametrize('role', ['operator', 'pracownik', 'stepnpio'])
def test_employee_receipt_uses_canonical_service(app, role):
    from app.services.pallets.pallet_confirmation_service import PalletConfirmationService
    with app.test_request_context('/', method='POST', data={'waga_palety': '125,5', 'lokalizacja': 'MGW01'}):
        session.update(zalogowany=True, rola=role, grupa='PSD')
        with patch('app.services.magazyn_dostawy.acceptance_service.AcceptanceService.accept_production_pallet', return_value=(True, 'OK')) as receive:
            result = PalletConfirmationService.potwierdz_palete(7, 'PSD', 'policy-test', app, None, None, True, '/')
    assert result[1] == 200
    receive.assert_called_once_with(7, 'MGW01', linia='PSD', login='policy-test', confirmed_weight=125.5)


@pytest.mark.parametrize('role', ['operator', 'pracownik', 'stepnpio'])
def test_order_and_picking_roles_are_equivalent(role):
    from app.services.warehouse_order_service import WarehouseOrderService
    from app.services.picking_service import PickingService
    service = WarehouseOrderService()
    service._repository = MagicMock()
    service._repository.get_by_id.return_value = {'id': 7}
    service._repository.delete.return_value = 1
    assert service.delete_order(7, role)[0]
    picking = PickingService()
    picking._picking_repo = MagicMock()
    picking._picking_repo.get_by_order_ref.return_value = [{'id': 7}]
    picking._picking_repo.delete_order.return_value = 1
    assert picking.delete_picking_order('TEST', role)[0]


def test_unknown_role_cannot_delete_picking_order():
    from app.services.picking_service import PickingService
    service = PickingService()
    service._picking_repo = MagicMock()
    assert not service.delete_picking_order('TEST', 'unknown')[0]
    service._picking_repo.get_by_order_ref.assert_not_called()


@pytest.mark.parametrize('role', ['operator', 'pracownik', 'magazynier'])
def test_direct_print_of_shared_label_ignores_production_hall(app, role):
    from app.blueprints.scanner import scanner_bp
    app.register_blueprint(scanner_bp)
    client = app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True, rola=role, grupa='PSD', login='policy-test')
    printer = MagicMock()
    printer.last_job_id = 123
    printer.print_pallet_label.return_value = (True, 'queued')
    with patch('app.services.scanner_service.ScannerService.get_label_data', return_value={
            'id': 7, 'nr_palety': 'TEST7', 'linia': None, 'typ': 'OPAKOWANIE'}), patch(
            'app.blueprints.scanner.base.get_printer', return_value=printer):
        response = client.post('/agro/scanner/print', json={
            'sscc': 'TEST7', 'pallet_type': 'Opakowanie', 'linia': 'AGRO'})
    assert response.status_code == 200
    assert response.json['success']
    printer.print_pallet_label.assert_called_once()


@pytest.mark.parametrize('amount', [10, 100])
def test_employee_can_consume_lp01_material_with_history(app, amount):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = {'id': 7, 'nr_palety': 'TEST7', 'nazwa': 'Kalka', 'lokalizacja': 'LP01', 'stan_magazynowy': 100}
    with patch('app.services.lp01_service.get_db_connection', return_value=conn), patch(
            'app.services.magazyn_dostawy.commands.pallet_lock_manager.PalletLockManager.has_quality_or_manual_block', return_value=False):
        result = Lp01Service.archive_lp01_item(7, consumed_qty=amount, user_login='policy-test')
    assert result[0], result[1]
    conn.commit.assert_called_once()
    assert any('INSERT INTO magazyn_archiwum' in call.args[0] for call in conn.cursor.return_value.execute.call_args_list)
    assert any('INSERT INTO palety_historia' in call.args[0] for call in conn.cursor.return_value.execute.call_args_list)


@pytest.mark.parametrize('location', ['BB03', 'MZ07', 'LP01', 'MASZYNA'])
def test_consumption_accepts_real_production_locations(app, location):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = {'id': 7, 'nr_palety': 'TEST7', 'nazwa': 'Test', 'lokalizacja': location, 'stan_magazynowy': 100}
    with app.test_request_context('/'):
        session.update(zalogowany=True, rola='pracownik', grupa='PSD')
        with patch('app.services.production_consumption_service.get_db_connection', return_value=conn), patch(
                'app.services.magazyn_dostawy.commands.pallet_lock_manager.PalletLockManager.has_quality_or_manual_block', return_value=False), patch(
                'app.repositories.warehouse_movement_ledger_repository.WarehouseMovementLedgerRepository.record_movement'):
            result = ProductionConsumptionService.consume_and_archive_pallet(7, 'Opakowanie', 'AGRO', 'policy-test')
    assert result[0], result[1]
    conn.commit.assert_called_once()


@pytest.mark.parametrize('role', ['operator', 'pracownik'])
@pytest.mark.parametrize('source', ['old', 'new'])
def test_worker_cannot_bypass_archive_guard_on_storage_stock(app, role, source):
    from app.services.warehouse_v2_service import WarehouseV2Service
    from app.services.warehouse_v2.pallet_status_service import PalletStatusService
    service = WarehouseV2Service if source == 'old' else PalletStatusService
    module = 'app.services.warehouse_v2_service' if source == 'old' else 'app.services.warehouse_v2.pallet_status_service'
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = {'id': 7, 'nr_palety': 'TEST7', 'nazwa': 'Test', 'lokalizacja': 'R010101', 'stan_magazynowy': 100}
    with app.test_request_context('/'):
        session.update(zalogowany=True, rola=role, grupa='PSD')
        with patch(module + '.get_db_connection', return_value=conn):
            result = service.archive_pallet(7, 'Opakowanie', 'policy-test', 'AGRO')
    assert not result[0]
    conn.commit.assert_not_called()
    assert not any(call.args[0].strip().startswith(('INSERT', 'UPDATE', 'DELETE')) for call in conn.cursor.return_value.execute.call_args_list)


def test_missing_role_cannot_delete_picking_order():
    from app.services.picking_service import PickingService
    service = PickingService()
    service._picking_repo = MagicMock()
    assert not service.delete_picking_order('TEST', None)[0]
    service._picking_repo.get_by_order_ref.assert_not_called()
