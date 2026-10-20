# MQTT telemetry without production daemons

For the web application on QNAP, set `ENABLE_MQTT_BRIDGE=true` and keep
`ENABLE_BACKGROUND_DAEMONS=false` to receive MQTT telemetry without starting
automatic pallet registration or the print queue. Configure the existing
`MQTT_BROKER_HOST`, `MQTT_BROKER_PORT`, `MQTT_BROKER_USERNAME` and
`MQTT_BROKER_PASSWORD` in the private deployment environment.

The default remains the background-daemon setting for compatibility. Set the
MQTT flag explicitly when telemetry and hardware automation need different
settings. Tests and the development reloader parent do not start the bridge.
Keep both flags disabled in isolated test applications.

The MQTT bridge only subscribes on startup. Receiving telemetry does not start
hardware daemons or printing. Existing explicit machine-command endpoints retain
their authorization checks. Report scheduling has its own independent switch.
