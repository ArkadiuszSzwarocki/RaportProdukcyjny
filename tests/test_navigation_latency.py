"""Navigation reads do not wait for queue writes or menu-counter queries."""
from datetime import datetime
from unittest.mock import MagicMock, patch
from flask import Blueprint, Flask, session
from app.core import contexts
from app.blueprints.planista.buffer import register_planista_buffer_routes


def test_buffer_navigation_reads_without_synchronizing_production():
    app = Flask(__name__)
    app.secret_key = 'isolated-navigation-check'
    blueprint = Blueprint('planista', __name__)
    register_planista_buffer_routes(blueprint)
    app.register_blueprint(blueprint)
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [(1, 2, '2026-10-24', 'Test', 'Order', 'mix', 1, 100, 90, datetime(2026, 10, 24, 8), 'w toku', 90, 20)]
    with app.test_client() as client, patch('app.blueprints.planista.buffer.get_db_connection', return_value=conn), patch('app.blueprints.planista.buffer.refresh_bufor_queue') as sync, patch('app.blueprints.planista.buffer.render_template', return_value='Buffer ready') as render:
        with client.session_transaction() as state:
            state.update(zalogowany=True, rola='masteradmin')
        assert client.get('/bufor?linia=AGRO&data=2026-10-24').status_code == 200
        sync.assert_not_called()
        conn.commit.assert_not_called()
        assert len(conn.cursor.return_value.execute.call_args_list) == 1
        assert conn.cursor.return_value.execute.call_args.args[0].lstrip().startswith('SELECT')
        row = render.call_args.kwargs['bufor_list'][0]
        assert row['spakowane'] == 20
        assert row['pozostalo_do_spakowania'] == 70
        conn.close.assert_called_once()


def test_menu_counts_never_fetch_during_html_render_and_mask_admin_data():
    app = Flask(__name__)
    app.secret_key = 'isolated-counters-check'
    cached = {'pending_orders_count': {'val': {'pending_orders_count': 3}, 'ts': 0}, 'system_errors_count': {'val': {'system_errors_count': 7}, 'ts': 0}}
    with patch.dict(contexts._CONTEXT_CACHE, {}, clear=True), patch.object(contexts, '_get_cached_context', side_effect=AssertionError('Must not query counters while rendering')):
        with app.test_request_context('/'):
            session.update(zalogowany=True, rola='masteradmin')
            assert contexts.inject_navigation_counters()['pending_orders_count'] == 0
            contexts._CONTEXT_CACHE.update(cached)
            assert contexts.inject_navigation_counters()['pending_orders_count'] == 3
            assert contexts.inject_navigation_counters()['system_errors_count'] == 7
            session['rola'] = 'pracownik'
            assert contexts.inject_navigation_counters()['system_errors_count'] == 0


def test_picking_badge_counts_shortages_without_loading_or_reserving_orders():
    import sqlite3
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE magazyn_kompletacja(order_ref TEXT, operator_login TEXT, status TEXT, paleta_id INTEGER)')
    conn.executemany('INSERT INTO magazyn_kompletacja VALUES (?,?,?,?)', [
        ('A', 'one', 'OCZEKUJE', 1), ('A', 'one', 'OCZEKUJE', 2),
        ('A', 'two', 'OCZEKUJE', 3), ('B', 'one', 'POMINIETA', 0),
        ('C', 'one', 'POMINIETA', 5), ('D', 'one', 'SKOMPLETOWANA', 6)])
    with patch('app.db.get_db_connection', return_value=conn):
        assert contexts._fetch_pending_picking_count() == {'pending_picking_count': 3}


def test_async_badge_response_fills_the_html_snapshot_without_picking_sync():
    from app.blueprints.warehouse_v2 import api_orders
    app = Flask(__name__)
    app.secret_key = 'isolated-badge-api-check'
    with app.test_request_context('/api/sidebar-badges?fresh=1'), patch.dict(contexts._CONTEXT_CACHE, {}, clear=True), patch.object(contexts, '_fetch_delivery_counters', return_value={'pending_deliveries': {'ALL': 2}}), patch.object(contexts, '_fetch_osip_transfers_count', return_value={'osip_transfers_count': 1}), patch.object(contexts, '_fetch_pending_orders_count', return_value={'pending_orders_count': 4}), patch.object(contexts, '_fetch_pending_picking_count', return_value={'pending_picking_count': 3}), patch.object(contexts, 'inject_bug_report_counters', return_value={}), patch.object(contexts, 'inject_system_errors_count', return_value={}), patch.object(api_orders._picking_service, 'get_active_orders', side_effect=AssertionError('No reservations while counting')):
        session.update(zalogowany=True, rola='masteradmin')
        response = api_orders.api_sidebar_badges().get_json()
        assert response['orders_nowe'] == 4
        assert response['active_picking'] == 3
        assert contexts.inject_navigation_counters()['pending_deliveries']['ALL'] == 2
        assert contexts.inject_navigation_counters()['pending_orders_count'] == 4


def test_picking_entry_does_not_synchronize_every_order_before_render():
    from app.blueprints.warehouse_v2 import views
    app = Flask(__name__)
    orders = [{'order_ref': 'TEST', 'pending_items': 1}]
    with app.test_request_context('/warehouse-v2/kompletacja?linia=AGRO'), patch('app.repositories.picking_repository.PickingRepository.get_active_orders', return_value=orders) as read, patch('app.services.picking_service.PickingService.get_active_orders', side_effect=AssertionError('No sync on page entry')), patch.object(views, 'render_template', return_value='ready') as render:
        assert views.kompletacja() == 'ready'
        read.assert_called_once_with()
        assert render.call_args.kwargs['initial_order_ref'] == 'TEST'
        assert render.call_args.kwargs['active_orders'] == orders


def test_server_timing_available_without_enabling_slow_request_logs():
    from app.core.middleware import record_request_start_time, log_slow_requests
    app = Flask(__name__)
    app.before_request(record_request_start_time(app))
    app.after_request(log_slow_requests(app))
    app.add_url_rule('/probe', view_func=lambda: 'ready')
    with patch('app.core.middleware.time.perf_counter', side_effect=[100, 100.125]):
        response = app.test_client().get('/probe')
    assert response.headers['Server-Timing'] == 'app;dur=125.0'


def test_dashboard_reuses_existing_plan_result_and_releases_connection_on_error():
    from contextlib import ExitStack
    from app.blueprints.main import index_data
    from app.services.dashboard_service import DashboardService
    today = datetime(2026, 10, 24).date()
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    staff = {'wszyscy': [], 'dostepni': [], 'obsada': []}
    work = ([[7, 'Test']], {'pallets': []}, 200, 30)
    zasyp = ([], {}, 100, 50)
    values = {'get_basic_staff_data': staff, 'get_hr_and_leave_data': {'wnioski_pending': []},
              'get_journal_entries': [], 'get_zasyp_started_products': [],
              'get_quality_and_leave_requests': {}, 'get_shift_notes': [],
              'get_full_plan_results_for_sections': (zasyp, work),
              'any_plan_in_progress': False, 'get_buffer_queue': {},
              'get_first_workowanie_map': {}, 'get_zasyp_product_order': [],
              'get_zasyp_active_status': False, 'get_active_products': [], 'get_next_workowanie_id': 7}
    with ExitStack() as stack:
        stack.enter_context(patch.object(index_data, 'get_db_connection', return_value=conn))
        stack.enter_context(patch.object(index_data, 'get_unfinished_section_orders', return_value=[]))
        for method, value in values.items():
            stack.enter_context(patch.object(DashboardService, method, return_value=value))
        duplicate = stack.enter_context(patch.object(DashboardService, 'get_production_plans', side_effect=AssertionError('Duplicate plan read')))
        result = index_data.build_dashboard_halls_context(today, 'Workowanie', 'AGRO', 'masteradmin')
        hall = result['halls_data']['AGRO']
        assert hall['plan_dnia'] is work[0]
        assert hall['palety_mapa'] is work[1]
        assert (hall['suma_plan'], hall['suma_wykonanie']) == (200, 30)
        duplicate.assert_not_called()
        conn.close.assert_called_once()
        conn.reset_mock()
        stack.enter_context(patch.object(DashboardService, 'get_journal_entries', side_effect=RuntimeError('read failed')))
        import pytest
        with pytest.raises(RuntimeError, match='read failed'):
            index_data.build_dashboard_halls_context(today, 'Workowanie', 'AGRO', 'masteradmin')
        conn.close.assert_called_once()


def test_borrowed_read_cursor_never_opens_or_closes_another_connection():
    from app.utils.queries_split.hr import HRQueries
    from app.utils.queries_split.production import ProductionQueries
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    with patch('app.utils.queries_split.hr.get_db_connection', side_effect=AssertionError('Extra connection')), patch('app.utils.queries_split.production.get_db_connection', side_effect=AssertionError('Extra connection')):
        assert HRQueries.get_pending_leave_requests(cursor=cursor) == []
        assert ProductionQueries.get_dziennik_zmiany('2026-10-24', 'Zasyp', cursor=cursor) == []
    cursor.close.assert_not_called()


def test_staff_assignments_read_once_and_keep_availability():
    from app.services.staff_service import StaffService
    with patch('app.services.staff_service.QueryHelper.get_pracownicy', return_value=[(1, 'A'), (2, 'B')]), patch('app.services.staff_service.QueryHelper.get_obsada_zmiany', return_value=[(2,)]) as assignments:
        data = StaffService.get_basic_staff_data('2026-10-24', cursor=MagicMock())
    assignments.assert_called_once()
    assert data['dostepni'] == [(1, 'A')]
    assert data['obsada'] == [(2,)]


def test_failed_plan_read_returns_owned_connection_to_pool():
    import pytest
    from app.services.production_service import ProductionService
    conn = MagicMock()
    with patch('app.services.production_service.get_db_connection', return_value=conn), patch('app.services.production_service.QueryHelper.get_plan_produkcji', side_effect=RuntimeError('read failed')):
        with pytest.raises(RuntimeError, match='read failed'):
            ProductionService.get_production_plans(datetime(2026, 10, 24).date(), 'Workowanie', 'AGRO')
    conn.close.assert_called_once()


def test_global_overview_loads_only_visible_data_on_one_connection():
    from app.blueprints.main import index_data
    from app.services.production_service import ProductionService
    conn = MagicMock()
    with patch.object(index_data, 'get_db_connection', return_value=conn) as acquire, patch.object(ProductionService, 'get_production_plans', return_value=([], {}, 0, 0)) as plans, patch.object(index_data.DashboardService, 'get_shift_notes', return_value=[{'note': 'Test'}]), patch.object(index_data.DashboardService, 'get_hr_and_leave_data', side_effect=AssertionError('Unused HR reads')), patch('app.services.ipomiar_service.read_dashboard', return_value=[]):
        data = index_data.build_production_overview_context(datetime(2026, 10, 24).date(), 'AGRO', 'masteradmin')
    acquire.assert_called_once()
    assert plans.call_count == 2
    assert all(call.kwargs['include_details'] is False for call in plans.call_args_list)
    assert data['shift_notes'] == [{'note': 'Test'}]
    assert data['halls_to_fetch'] == ['AGRO']
    conn.close.assert_called_once()


def test_overview_skips_histories_but_keeps_plan_rows_and_start_requirements():
    from app.services.production_service import ProductionService
    from copy import deepcopy
    row = [1, 'Test', 100, 'zaplanowane', None, None, 0, 20, 1, 'worki_25', '', 0, '', None, None, 0, 'krajowa', '', 'Opakowanie', 'Etykieta']
    def requirements(plans, line, cursor):
        plans[0][20] = 'Opakowanie'
        plans[0][21] = 'Etykieta'
    with patch('app.services.production_service.QueryHelper.get_plan_produkcji', return_value=deepcopy([row])), patch.object(ProductionService, '_get_transfer_map', return_value={}), patch.object(ProductionService, '_sync_sections_weights'), patch.object(ProductionService, '_populate_agro_start_requirements', side_effect=requirements), patch.object(ProductionService, '_populate_carry_over_tonaz', side_effect=AssertionError('Unused carry-over detail')), patch.object(ProductionService, '_aggregate_final_results', side_effect=AssertionError('Unused pallet/batch histories')):
        plans, details, _, _ = ProductionService.get_production_plans(datetime(2026, 10, 24).date(), 'Workowanie', 'AGRO', cursor=MagicMock(), include_details=False)
    assert plans[0][:4] == row[:4]
    assert plans[0][7] == 20
    assert plans[0][20:22] == ['Opakowanie', 'Etykieta']
    assert details == {}


def test_connectivity_ping_does_not_depend_on_database():
    from app.blueprints.api.health import register_api_health_routes
    app = Flask(__name__)
    blueprint = Blueprint('probe', __name__, url_prefix='/api')
    register_api_health_routes(blueprint)
    app.register_blueprint(blueprint)
    with patch('app.blueprints.api.health.get_db_connection', side_effect=RuntimeError('Database unavailable')) as db:
        response = app.test_client().get('/api/ping')
    assert response.status_code == 200
    assert response.get_json() == {'status': 'UP'}
    assert response.headers['Cache-Control'] == 'no-store'
    db.assert_not_called()
