"""Telemetry may run with hardware daemons disabled and vice versa."""
from unittest.mock import MagicMock, patch

import pytest

from app.core import factory


@pytest.mark.parametrize('mqtt_enabled,background_enabled', [
    ('true', 'false'), ('false', 'true'), ('false', 'false'), ('true', 'true'),
])
def test_mqtt_startup_is_independent(monkeypatch, mqtt_enabled, background_enabled):
    monkeypatch.delenv('PYTEST_CURRENT_TEST', raising=False)
    monkeypatch.setenv('FLASK_ENV', 'production')
    monkeypatch.setenv('ENABLE_MQTT_BRIDGE', mqtt_enabled)
    monkeypatch.setenv('ENABLE_BACKGROUND_DAEMONS', background_enabled)
    with patch('app.services.mqtt_service.start_mqtt_bridge') as mqtt, patch(
            'app.core.factory.start_daemon_threads') as hardware, patch(
            'app.core.report_daemon.start_report_scheduler'):
        factory._maybe_start_background_daemons(MagicMock(), False)
    assert mqtt.call_count == int(mqtt_enabled == 'true')
    assert hardware.call_count == int(background_enabled == 'true')


def test_reloader_parent_never_starts_mqtt(monkeypatch):
    monkeypatch.delenv('PYTEST_CURRENT_TEST', raising=False)
    monkeypatch.setenv('ENABLE_MQTT_BRIDGE', 'true')
    with patch('app.services.mqtt_service.start_mqtt_bridge') as mqtt:
        factory._maybe_start_background_daemons(MagicMock(), True)
    mqtt.assert_not_called()
