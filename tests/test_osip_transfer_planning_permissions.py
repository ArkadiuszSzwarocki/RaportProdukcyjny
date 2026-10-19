from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask

from app.blueprints.osip import osip_bp


@pytest.fixture
def transfer_client():
    app = Flask(__name__)
    app.secret_key = 'transfer-permission-test'
    app.register_blueprint(osip_bp)
    client = app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True, login='osip-worker', rola='magazynier', subrole='OSIP')
    return client


def test_osip_lookup_requires_source_warehouse_permission_instead_of_pallet_production_line(transfer_client):
    with patch('app.core.production_permissions._page_allowed', side_effect=lambda line, *a, **kw: line == 'OSIP') as permission, \
         patch('app.blueprints.osip.routes.transfer_service.lookup_transfer_pallet', return_value={'nr_palety': 'SUR-1', 'requested_qty': 100}) as lookup:
        response = transfer_client.get('/osip/api/transfers/lookup-pallet?source=OSIP&code=SUR-1')
    assert response.status_code == 200
    permission.assert_called_once_with('OSIP', 'magazyn', write=False)
    lookup.assert_called_once_with('SUR-1', 'OSIP')


def test_osip_worker_cannot_read_central_stock_by_changing_lookup_source(transfer_client):
    with patch('app.core.production_permissions._page_allowed', side_effect=lambda line, *a, **kw: line == 'OSIP'), \
         patch('app.blueprints.osip.routes.transfer_service.lookup_transfer_pallet') as lookup:
        response = transfer_client.get('/osip/api/transfers/lookup-pallet?source=MS01&code=SUR-1')
    assert response.status_code == 403
    lookup.assert_not_called()


def test_edit_requires_write_permission_for_actual_transfer_source(transfer_client):
    transfer = SimpleNamespace(source_warehouse='MS01', destination_warehouse='OSIP')
    with patch('app.blueprints.osip.routes.transfer_service.repository.get_transfer_by_id', return_value=transfer), \
         patch('app.core.production_permissions._page_allowed', side_effect=lambda line, *a, **kw: line == 'OSIP'), \
         patch('app.blueprints.osip.routes.transfer_service.update_planned_transfer') as update:
        response = transfer_client.put('/osip/api/transfers/1', json={'source_warehouse':'OSIP', 'items':[]})
    assert response.status_code == 403
    update.assert_not_called()
