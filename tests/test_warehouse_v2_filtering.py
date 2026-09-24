from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
RENDERING_TEMPLATES_JS = ROOT / 'static' / 'js' / 'warehouse_v2' / 'rendering_templates.js'
RENDERING_LOGIC_JS = ROOT / 'static' / 'js' / 'warehouse_v2' / 'rendering_logic.js'


def test_is_match_does_not_short_circuit_on_empty_filter():
    content = RENDERING_TEMPLATES_JS.read_text(encoding='utf-8')

    # Ensure we don't have the bug where empty filter string bypassed locationFiltersArray
    assert 'if (filterText === "") return true;' not in content
    assert 'if (filterText !== "") {' in content


def test_is_match_checks_location_filters_array_when_provided():
    content = RENDERING_TEMPLATES_JS.read_text(encoding='utf-8')

    assert 'if (Array.isArray(locationFiltersArray))' in content
    assert 'allowsPending' in content
    assert 'isPendingOrEmpty' in content


def test_populate_location_filter_includes_oczekujace():
    content = RENDERING_LOGIC_JS.read_text(encoding='utf-8')

    assert "uniqueLocationsSet.add('OCZEKUJĄCE')" in content
