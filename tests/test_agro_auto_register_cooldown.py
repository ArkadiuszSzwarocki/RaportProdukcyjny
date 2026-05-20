from app.services.agro_warehouse_service import _get_auto_pallet_cooldown_seconds


def test_auto_pallet_cooldown_defaults_to_zero(monkeypatch):
    monkeypatch.delenv('AGRO_AUTO_PALLET_COOLDOWN_SECONDS', raising=False)

    assert _get_auto_pallet_cooldown_seconds() == 0.0


def test_auto_pallet_cooldown_reads_positive_value(monkeypatch):
    monkeypatch.setenv('AGRO_AUTO_PALLET_COOLDOWN_SECONDS', '7.5')

    assert _get_auto_pallet_cooldown_seconds() == 7.5


def test_auto_pallet_cooldown_invalid_value_falls_back_to_zero(monkeypatch):
    monkeypatch.setenv('AGRO_AUTO_PALLET_COOLDOWN_SECONDS', 'abc')

    assert _get_auto_pallet_cooldown_seconds() == 0.0
