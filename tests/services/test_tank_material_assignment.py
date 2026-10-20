"""Only the full assigned material name may pass an active tank rule."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.tank_validation_service import TankValidationService


@pytest.mark.parametrize('name,allowed', [
    ('ACP Serwatka KwaĹ›na', True), (' acp  serwatka kwaĹ›na ', True),
    ('Inny surowiec', False), ('Alfa', False), ('ACP Serwatka KwaĹ›na Extra', False), ('', False),
])
def test_bb19_rejects_other_or_partial_material_names(name, allowed):
    rule = SimpleNamespace(is_active=True, nazwa_surowca='ACP Serwatka KwaĹ›na')
    with patch('app.services.tank_validation_service.TankValidationRepository.get_rule_by_tank', return_value=rule):
        result, error = TankValidationService.validate_tank_material('BB19', name)
    assert result is allowed
    assert bool(error) is not allowed


def test_explicitly_disabled_rule_explains_bb19_unrestricted_behavior():
    rule = SimpleNamespace(is_active=False, nazwa_surowca='ACP Serwatka KwaĹ›na')
    with patch('app.services.tank_validation_service.TankValidationRepository.get_rule_by_tank', return_value=rule):
        assert TankValidationService.validate_tank_material('BB19', 'Inny surowiec') == (True, None)
