import pytest

from app.services import mqtt_service


def test_mqtt_password_is_required(monkeypatch):
    monkeypatch.delenv("MQTT_BROKER_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="MQTT_BROKER_PASSWORD"):
        mqtt_service._get_required_mqtt_password()


def test_mqtt_password_is_loaded_from_environment(monkeypatch):
    monkeypatch.setenv("MQTT_BROKER_PASSWORD", "configured-secret")

    assert mqtt_service._get_required_mqtt_password() == "configured-secret"


def test_blank_mqtt_password_is_rejected(monkeypatch):
    monkeypatch.setenv("MQTT_BROKER_PASSWORD", "   ")

    with pytest.raises(RuntimeError, match="MQTT_BROKER_PASSWORD"):
        mqtt_service._get_required_mqtt_password()
