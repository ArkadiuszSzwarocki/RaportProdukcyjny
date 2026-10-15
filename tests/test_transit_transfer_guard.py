# cspell:words sscc
"""A second transfer cannot reserve or move stock still owned by OSIP."""
import json
from unittest.mock import MagicMock, patch

from flask import Flask, session
import pytest

from app.services.magazyn_dostawy.commands.delivery_order_validator import DeliveryOrderValidator, is_transit_location, TransitPalletError
from app.services.magazyn_dostawy.commands.pallet_lock_manager import PalletLockManager
from app.services.magazyn_dostawy.commands.live_transfer_service import LiveTransferService
from app.services.magazyn_dostawy.commands.delivery_save_service import DeliverySaveService
from app.services.magazyn_dostawy.commands.internal_transfer_processor import InternalTransferProcessor

CODE = 'SUR000000000000000001'


def stock_cursor(location='W_TRANZYCIE_OSIP', osip=False):
    cursor = MagicMock()
    document = {'id':'wrong-mm','status':'OCZEKUJE','items':'[]','order_ref':'TEST-TRANSIT-MM',
                'linia':'PSD','supplier':''}
    row = dict(id=4092,nr_palety=CODE,lokalizacja=location,stan_magazynowy=1000,nazwa='Test Mix')
    def fetchone():
        query = cursor.execute.call_args.args[0]
        if query.startswith('SELECT') and 'FROM magazyn_dostawy WHERE id' in query:
            return dict(document)
        if 'FROM osip_transfer_items' in query:
            return {'id':12} if osip else None
        if 'FROM magazyn_surowce ' in query and 'LIMIT 1' in query:
            return dict(row)
        return None
    def fetchall():
        query = cursor.execute.call_args.args[0]
        if 'FROM magazyn_surowce ' in query and 'FOR UPDATE' in query:
            return [dict(row)]
        return []
    cursor.fetchone.side_effect = fetchone
    cursor.fetchall.side_effect = fetchall
    return cursor


@pytest.mark.parametrize('value', ['W_TRANZYCIE_OSIP','w-tranzycie-osip',' W TRANZYCIE ','W_TRANZYCIE'])
def test_transit_markers_are_not_physical_source_locations(value):
    assert is_transit_location(value)
    ok, message = DeliveryOrderValidator.validate({},[dict(sourceSpot=value)],False,'',[value],True)
    assert not ok and 'tranzycie' in message


@pytest.mark.parametrize('location,osip', [('W_TRANZYCIE_OSIP',False),('W_TRANZYCIE',False),('MS01',True)])
def test_reservation_checks_locked_stock_and_active_osip_even_with_forged_source(location, osip):
    cursor = stock_cursor(location,osip)
    with patch('app.core.logistics_permissions.logistics_stock_write_allowed',return_value=True):
        with pytest.raises(TransitPalletError):
            PalletLockManager.set_pallets_blocked(cursor,[dict(nr_palety=CODE,sourceTable='magazyn_surowce',sourceSpot='MP01')],1)
    assert 'FOR UPDATE' in cursor.execute.call_args_list[0].args[0]
    assert not any(c.args[0].startswith('UPDATE') for c in cursor.execute.call_args_list)


def test_releasing_wrong_mm_never_clears_transit_block_even_without_transfer_metadata():
    cursor = stock_cursor()
    with patch('app.core.logistics_permissions.logistics_stock_write_allowed',return_value=True):
        PalletLockManager.set_pallets_blocked(cursor,[dict(nr_palety=CODE,sourceTable='magazyn_surowce')],0,exclude_delivery_id='wrong-mm')
    assert not any(c.args[0].startswith('UPDATE') for c in cursor.execute.call_args_list)


def test_available_stock_can_still_be_reserved_and_settled_items_are_not_reserved_again():
    cursor = stock_cursor('MS01')
    with patch('app.core.logistics_permissions.logistics_stock_write_allowed',return_value=True):
        PalletLockManager.set_pallets_blocked(cursor,[dict(nr_palety=CODE,sourceTable='magazyn_surowce')],1)
    assert any(c.args[0].startswith('UPDATE magazyn_surowce') for c in cursor.execute.call_args_list)
    cursor.reset_mock()
    PalletLockManager.set_pallets_blocked(cursor,[dict(nr_palety=CODE,accepted=True)],1)
    cursor.execute.assert_not_called()


def test_live_append_rolls_back_before_document_or_fulfillment_write():
    connection = MagicMock()
    cursor = stock_cursor()
    connection.cursor.return_value = cursor
    with patch('app.services.magazyn_dostawy.commands.live_transfer_service.get_db_connection',return_value=connection), patch(
        'app.core.logistics_permissions.logistics_stock_write_allowed',return_value=True), patch(
        'app.services.warehouse_order_fulfillment.WarehouseOrderFulfillment.sync_transfer') as fulfillment:
        ok, message = LiveTransferService.add_live_transfer_item('wrong-mm',dict(nr_palety=CODE,sourceSpot='MP01',sourceTable='magazyn_surowce'))
    assert not ok and 'tranzycie' in message
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    fulfillment.assert_not_called()
    assert not any(c.args[0].startswith(('UPDATE','INSERT')) for c in cursor.execute.call_args_list)


@pytest.mark.parametrize('skip', [False,True])
def test_final_save_cannot_bypass_actual_stock_transit(skip):
    connection = MagicMock()
    cursor = stock_cursor()
    connection.cursor.return_value = cursor
    with patch('app.services.magazyn_dostawy.commands.delivery_save_service.get_db_connection',return_value=connection), patch(
        'app.core.logistics_permissions.logistics_stock_write_allowed',return_value=True):
        ok, message = DeliverySaveService.save_dostawa(dict(id='wrong-mm',linia='PSD',skip_warehouse_lookup=skip,
            items=[dict(id='new',nr_palety=CODE,sourceSpot='MP01',productName='Test Mix',sourceTable='magazyn_surowce')]))
    assert not ok and 'tranzycie' in message
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()


def test_processor_rechecks_actual_location_before_adding_movement_history():
    cursor = stock_cursor()
    with patch.object(InternalTransferProcessor,'_is_pallet_archived_or_zero',return_value=(False,'')), patch.object(
        InternalTransferProcessor,'_find_active_pallet_by_sscc',return_value=(dict(id=4092,nr_palety=CODE,lokalizacja='W_TRANZYCIE_OSIP'),'surowiec','magazyn_surowce')), patch(
        'app.core.logistics_permissions.logistics_stock_write_allowed',return_value=True):
        ok, message = InternalTransferProcessor.process_transfer(cursor,[dict(id='new',nr_palety=CODE,sourceSpot='MP01')],'PSD','wrong-mm','MS01','REF',True,'test')
    assert not ok and 'tranzycie' in message
    assert not any(c.args[0].startswith(('UPDATE','INSERT')) for c in cursor.execute.call_args_list)


@pytest.mark.parametrize('skip', [False,True])
def test_lookup_hides_transit_and_active_osip_stock_and_explains_exact_search(skip):
    from app.blueprints.magazyn_dostawy.routes import pallets as module
    app = Flask(__name__)
    app.secret_key = 'transit-lookup-unit-test'
    cursor = MagicMock()
    rows = [dict(id=4092,nr_palety=CODE,nazwa='WPP',stan_magazynowy=1000,lokalizacja='W_TRANZYCIE_OSIP',type='surowiec'),
            dict(id=4093,nr_palety='PLANNED-OSIP',nazwa='WPP',stan_magazynowy=1000,lokalizacja='MS01',type='surowiec')]
    def fetchall():
        query = cursor.execute.call_args.args[0]
        if 'FROM magazyn_surowce ' in query:
            return [dict(row) for row in rows]
        if 'FROM osip_transfer_items' in query:
            return [dict(nr_palety='PLANNED-OSIP')]
        return []
    cursor.fetchall.side_effect = fetchall
    connection = MagicMock()
    connection.cursor.return_value = cursor
    with app.test_request_context('/?linia=PSD&prefix='+CODE+'&skip_warehouse_lookup='+('1' if skip else '0')):
        session.update(zalogowany=True,rola='masteradmin')
        with patch.object(module,'get_db_connection',return_value=connection):
            response = module.get_available_pallets()
        assert response.json['success']
        assert response.json['pallets'] == []
        assert 'tranzycie' in response.json['unavailable_reason']
