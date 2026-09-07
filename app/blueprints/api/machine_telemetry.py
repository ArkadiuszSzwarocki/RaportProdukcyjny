from flask import Blueprint, jsonify, request
from app.services.machine_telemetry_service import MachineTelemetryService
from app.services.mqtt_service import simulate_machine_data
from app.decorators import login_required

def register_api_machine_telemetry_routes(bp: Blueprint):
    """Register REST API endpoints for machine broker telemetry and commands."""

    @bp.route('/machines/telemetry/live', methods=['GET'])
    @login_required
    def get_live_machine_telemetry():
        data = MachineTelemetryService.get_live_dashboard_data()
        return jsonify({
            'success': True,
            'data': data
        })

    @bp.route('/machines/telemetry/command', methods=['POST'])
    @login_required
    def send_machine_command():
        payload = request.get_json(silent=True) or {}
        topic = str(payload.get('topic', '')).strip()
        command_data = payload.get('command') or {}

        if not topic:
            return jsonify({'success': False, 'message': 'Wymagany jest temat MQTT (topic).'}), 400

        result = MachineTelemetryService.send_machine_command(topic=topic, command_payload=command_data)
        return jsonify(result.to_dict())

    @bp.route('/machines/palletizer/config', methods=['GET'])
    @login_required
    def get_palletizer_config():
        from app.services.pallet_pattern_service import PalletPatternService
        config = PalletPatternService.get_config()
        presets = PalletPatternService.get_presets()
        return jsonify({
            'success': True,
            'data': {
                'config': config,
                'presets': presets
            }
        })

    @bp.route('/machines/palletizer/config', methods=['POST'])
    @login_required
    def set_palletizer_config():
        from app.services.pallet_pattern_service import PalletPatternService
        from datetime import datetime
        payload = request.get_json(silent=True) or {}
        result = PalletPatternService.update_config(payload)
        
        # Also broadcast configuration change command to MQTT broker if active
        if result.success and payload.get('sync_to_machine', True):
            cfg = result.data or {}
            MachineTelemetryService.send_machine_command(
                topic="iot-2/type/cMT2108X2/id/agroPaletyzator/setPattern",
                command_payload={
                    "d": {
                        "receptura": cfg.get("preset_name", ""),
                        "typPalety": cfg.get("pallet_type", "INDUSTRIAL_100x120"),
                        "nazwaPalety": cfg.get("pallet_name", "Paleta Przemysłowa (1000 × 1200 mm)"),
                        "szerokoscM": cfg.get("pallet_width_m", 1.0),
                        "dlugoscM": cfg.get("pallet_length_m", 1.2),
                        "warstwyPelne": cfg.get("full_layers", 12),
                        "warstwyLacznie": cfg.get("total_layers", 13),
                        "workiNaWarstwe": cfg.get("bags_per_layer", 4),
                        "workiSzczyt": cfg.get("top_layer_bags", 2),
                        "lacznieWorkow": cfg.get("total_bags", 50),
                        "masaWorkaKg": cfg.get("bag_weight_kg", 25.0)
                    },
                    "ts": datetime.now().isoformat()
                }
            )

        return jsonify(result.to_dict()), (200 if result.success else 400)

    @bp.route('/machines/errors', methods=['GET'])
    @login_required
    def get_machine_errors():
        from app.services.machine_error_log_service import MachineErrorLogService
        machine = request.args.get('machine')
        severity = request.args.get('severity')
        limit = int(request.args.get('limit', 100))
        logs = MachineErrorLogService.get_errors(machine=machine, severity=severity, limit=limit)
        return jsonify({
            'success': True,
            'data': logs
        })

    @bp.route('/machines/errors/clear', methods=['POST'])
    @login_required
    def clear_machine_errors():
        from app.services.machine_error_log_service import MachineErrorLogService
        result = MachineErrorLogService.clear_logs()
        return jsonify(result.to_dict())

    @bp.route('/machines/errors/test', methods=['POST'])
    @login_required
    def test_log_error():
        from app.services.machine_error_log_service import MachineErrorLogService
        payload = request.get_json(silent=True) or {}
        machine = str(payload.get('machine', 'WAGOPAKOWACZKA')).strip()
        description = str(payload.get('description', 'Testowy błąd/alarm z panelu')).strip()
        severity = str(payload.get('severity', 'WARNING')).strip()
        code = str(payload.get('code', 'TEST-01')).strip()

        entry = MachineErrorLogService.log_error(
            machine=machine,
            description=description,
            severity=severity,
            code=code
        )
        return jsonify({'success': True, 'data': entry})

    @bp.route('/machines/rejects', methods=['GET'])
    @login_required
    def get_machine_rejects():
        from app.services.machine_reject_log_service import MachineRejectLogService
        reason = request.args.get('reason')
        limit = int(request.args.get('limit', 100))
        logs = MachineRejectLogService.get_rejects(limit=limit, reason_code=reason)
        stats = MachineRejectLogService.get_reject_statistics()
        return jsonify({
            'success': True,
            'data': {
                'logs': logs,
                'statistics': stats
            }
        })

    @bp.route('/machines/rejects/clear', methods=['POST'])
    @login_required
    def clear_machine_rejects():
        from app.services.machine_reject_log_service import MachineRejectLogService
        result = MachineRejectLogService.clear_logs()
        return jsonify(result.to_dict())

    @bp.route('/machines/rejects/test', methods=['POST'])
    @login_required
    def test_log_reject():
        from app.services.machine_reject_log_service import MachineRejectLogService
        payload = request.get_json(silent=True) or {}
        weight = float(payload.get('weight_kg', 24.15))
        target_w = float(payload.get('target_weight_kg', 25.0))
        reason = str(payload.get('reason_code', 'UNDERWEIGHT')).strip().upper()
        recipe = str(payload.get('recipe_name', 'Mieszanka Agro 25kg')).strip()

        entry = MachineRejectLogService.log_reject(
            weight_kg=weight,
            target_weight_kg=target_w,
            reason_code=reason,
            recipe_name=recipe,
            operator="Test Panelu Cyfrowego Bliźniaka"
        )
        return jsonify({'success': True, 'data': entry})

    @bp.route('/machines/telemetry/simulate', methods=['POST'])
    @login_required
    def simulate_telemetry():
        payload = request.get_json(silent=True) or {}
        add_counter = int(payload.get('add_counter', 5))
        add_pallets = int(payload.get('add_pallets', 1))
        status = str(payload.get('status', 'PRACA')).strip()

        simulate_machine_data(add_counter=add_counter, add_pallets=add_pallets, set_status=status)
        return jsonify({
            'success': True,
            'message': 'Zasymulowano impulsy z maszyny pakującej.'
        })
