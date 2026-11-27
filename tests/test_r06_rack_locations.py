from unittest.mock import MagicMock
from app.utils.location_validator import validate_registered_warehouse_location
from app.services.magazyn_dostawy.location_service import LocationService


def _mock_cursor(allowed_names):
    cur = MagicMock()
    cur.fetchall.return_value = [{'nazwa': name} for name in allowed_names]
    return cur


def test_r06_levels_4_and_5_are_allowed_when_r06_is_registered():
    cur = _mock_cursor(['R05', 'R06'])
    for loc in ('R060104', 'R060204', 'R060304', 'R060404', 'R060504', 'R060305', 'R060505', 'R050404'):
        ok, err = validate_registered_warehouse_location(cur, loc)
        assert ok is True, f'{loc} should be allowed, got: {err}'

    ok_bad, _ = validate_registered_warehouse_location(cur, 'R060106')
    assert ok_bad is False


def test_static_location_candidates_include_r06_row_4_and_5():
    candidates = LocationService._build_static_location_candidates()
    assert 'R060104' in candidates
    assert 'R060404' in candidates
    assert 'R060505' in candidates
    assert 'R050404' in candidates
    assert 'R060106' not in candidates

