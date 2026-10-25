# cspell:words nontransactional
"""Warehouse receipt and completion mail boundaries, without production connections."""
from datetime import date, timedelta
from unittest.mock import MagicMock
import pytest
from flask import Flask
from app.utils.pallet_receipt_rules import ensure_unique_stock_code, validate_pallet_dates
from app.utils.location_validator import validate_registered_warehouse_location
from app.services.warehouse_reports.warehouse_document_classifier import WarehouseDocumentClassifier


@pytest.mark.parametrize('source,target,expected',[
    ('MP01','R010101',True),('R010101','MS01',True),('MS01','BF_MP01',True),
    ('MS01','PSD01',False),('OSIP','MP01',False),('BB19','MP01',False)])
def test_individual_mail_requires_central_mm_involving_mp01(source,target,expected):
    document={'supplier':'','lokalizacja_z':source,'lokalizacja_do':target}
    items=[{'sourceSpot':source,'lokalizacja_przyjecia':target,'accepted':True}]
    assert WarehouseDocumentClassifier.is_automatic_mp01_mm(document,items) is expected


def test_external_delivery_does_not_queue_an_mm_email():
    document={'supplier':'External supplier','lokalizacja_z':'MS01','lokalizacja_do':'MP01'}
    assert not WarehouseDocumentClassifier.is_automatic_mp01_mm(document,[{'accepted':True}])


@pytest.mark.parametrize('location',['MP01-typo','R019999','R010000'])
def test_location_prefix_cannot_authorize_unknown_or_impossible_slot(location):
    cursor=MagicMock()
    cursor.fetchall.return_value=[{'nazwa':'MP01'},{'nazwa':'R01'}]
    assert not validate_registered_warehouse_location(cursor,location)[0]


def test_empty_location_dictionary_stops_receipt():
    cursor=MagicMock()
    cursor.fetchall.return_value=[]
    assert not validate_registered_warehouse_location(cursor,'MP01')[0]


def test_raw_stock_sscc_cannot_duplicate_packaging_identity():
    cursor=MagicMock()
    cursor.fetchone.return_value={'engine':'InnoDB'}
    cursor.fetchall.side_effect=[
        [{'nazwa':'MP01'}],
        [{'name':name} for name in ('magazyn_surowce','magazyn_opakowania','magazyn_dodatki','magazyn_palety')],
        [],[{'id':7}]]
    with pytest.raises(ValueError,match='magazyn_opakowania'):
        ensure_unique_stock_code(cursor,'SUR123')
    assert not any(call.args[0].startswith(('INSERT','UPDATE','DELETE')) for call in cursor.execute.call_args_list)


def test_nontransactional_registry_cannot_claim_serialized_receipt():
    cursor=MagicMock()
    cursor.fetchone.return_value={'engine':'MyISAM'}
    with pytest.raises(ValueError,match='InnoDB'):
        ensure_unique_stock_code(cursor,'SUR123')


@pytest.mark.parametrize('production,expiry',[('2025-02-30',None),('2025-01-02','2025-01-01')])
def test_invalid_receipt_dates_are_rejected(production,expiry):
    with pytest.raises(ValueError):
        validate_pallet_dates(production,expiry)


def test_future_production_date_is_rejected():
    with pytest.raises(ValueError):
        validate_pallet_dates((date.today()+timedelta(days=1)).isoformat(),None)


def test_all_scope_authorizes_logged_in_shared_stock_without_hall_ownership():
    from app.core.shared_raw_stock_permissions import shared_raw_stock_allowed
    from flask import session
    app = Flask(__name__)
    app.secret_key = 'shared-stock-test'
    with app.test_request_context('/'):
        assert not shared_raw_stock_allowed({'linia': 'AGRO', 'lokalizacja': 'MS01'}, 'ALL', write=True)
        session.update(zalogowany=True, rola='pracownik', grupa='OSIP')
        assert shared_raw_stock_allowed({'linia': 'AGRO', 'lokalizacja': 'MS01'}, 'ALL', write=True)


@pytest.mark.parametrize('role', ['pracownik', 'operator', 'laborant'])
def test_print_history_denies_non_management_roles(monkeypatch, role):
    from flask import session
    from app.blueprints.magazyn_dostawy.routes.document_monitoring import movement_print_history
    monitor = MagicMock()
    monkeypatch.setattr('app.repositories.movement_document_repository.MovementDocumentRepository.monitor', monitor)
    app = Flask(__name__)
    app.secret_key = 'warehouse-history-test'
    with app.test_request_context('/', headers={'Accept': 'application/json'}):
        session.update(zalogowany=True, rola=role, login='test-user')
        response = app.make_response(movement_print_history())
    assert response.status_code == 403
    monitor.assert_not_called()


@pytest.mark.parametrize('role', ['admin', 'masteradmin', 'zarzad', 'lider'])
def test_print_history_is_available_to_management(monkeypatch, role):
    from flask import session
    from app.blueprints.magazyn_dostawy.routes.document_monitoring import movement_print_history
    monitor = MagicMock(return_value=([], []))
    jobs = MagicMock(return_value={})
    render = MagicMock(return_value='history')
    monkeypatch.setattr('app.repositories.movement_document_repository.MovementDocumentRepository.monitor', monitor)
    monkeypatch.setattr('app.repositories.movement_print_job_repository.MovementPrintJobRepository.latest_for_documents', jobs)
    monkeypatch.setattr('app.blueprints.magazyn_dostawy.routes.document_monitoring.render_template', render)
    app = Flask(__name__)
    app.secret_key = 'warehouse-history-test'
    with app.test_request_context('/'):
        session.update(zalogowany=True, rola=role, login='test-user')
        assert app.make_response(movement_print_history()).status_code == 200
    monitor.assert_called_once_with('', 1, archived=False)
    render.assert_called_once()
