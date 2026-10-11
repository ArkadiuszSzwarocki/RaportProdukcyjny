import pytest
from app.core.factory import create_app
from app.services.warehouse_3d_service import Warehouse3dService


@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    return app


def test_rack_configurations_include_mp01_and_bfmp01():
    configs = Warehouse3dService.get_rack_configurations()
    rack_ids = [c['rack_id'] for c in configs]
    
    assert 'MP01' in rack_ids, "MP01 must be present in rack configurations"
    assert 'BFMP01' in rack_ids, "BFMP01 must be present in rack configurations"
    
    mp01 = next(c for c in configs if c['rack_id'] == 'MP01')
    assert mp01['rack_type'] == 'FLOOR_ZONE'
    assert mp01['columns'] >= 10
    assert mp01['levels'] >= 8
    
    bfmp01 = next(c for c in configs if c['rack_id'] == 'BFMP01')
    assert bfmp01['rack_type'] == 'BUFFER_ZONE'
    assert bfmp01['columns'] >= 6
    assert bfmp01['levels'] >= 5


def test_normalize_location_key_floor_zones():
    # Production floor zone variants
    assert Warehouse3dService._normalize_location_key('MP01') == 'MP01'
    assert Warehouse3dService._normalize_location_key('MPO1') == 'MP01'
    assert Warehouse3dService._normalize_location_key('MP-01') == 'MP01'
    assert Warehouse3dService._normalize_location_key('MP1') == 'MP01'
    assert Warehouse3dService._normalize_location_key('MP010101') == 'MP010101'
    
    # Buffer zone variants
    assert Warehouse3dService._normalize_location_key('BF_MP01') == 'BFMP01'
    assert Warehouse3dService._normalize_location_key('BFMP01') == 'BFMP01'
    assert Warehouse3dService._normalize_location_key('BF-MP01') == 'BFMP01'
    assert Warehouse3dService._normalize_location_key('BFMP010101') == 'BFMP010101'


def test_get_warehouse_3d_state_mp01(app):
    with app.app_context():
        state = Warehouse3dService.get_warehouse_3d_state(linia='ALL', rack_filter='MP01')
        assert state is not None
        assert state.get('success') is True
        assert len(state.get('racks', [])) == 1
        
        mp01_rack = state['racks'][0]
        assert mp01_rack['rack_id'] == 'MP01'
        assert mp01_rack['rack_type'] == 'FLOOR_ZONE'
        assert len(mp01_rack['slots']) >= 80
        
        # Verify slots structure
        first_slot = mp01_rack['slots'][0]
        assert 'column_index' in first_slot or 'column' in first_slot
        assert 'level_index' in first_slot or 'level' in first_slot
        assert 'location_code' in first_slot
        assert first_slot['location_code'].startswith('MP01')


def test_get_warehouse_3d_state_bfmp01(app):
    with app.app_context():
        state = Warehouse3dService.get_warehouse_3d_state(linia='ALL', rack_filter='BFMP01')
        assert state is not None
        assert state.get('success') is True
        assert len(state.get('racks', [])) == 1
        
        bf_rack = state['racks'][0]
        assert bf_rack['rack_id'] == 'BFMP01'
        assert bf_rack['rack_type'] == 'BUFFER_ZONE'
        assert len(bf_rack['slots']) >= 30


def test_get_warehouse_3d_state_all_includes_zones(app):
    with app.app_context():
        state = Warehouse3dService.get_warehouse_3d_state(linia='ALL', rack_filter='ALL')
        assert state is not None
        assert state.get('success') is True
        
        rack_ids = [r['rack_id'] for r in state.get('racks', [])]
        assert 'MP01' in rack_ids
        assert 'BFMP01' in rack_ids
        assert 'R01' in rack_ids
