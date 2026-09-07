# File: app/blueprints/admin/process_flow.py
"""Admin 3D Process Flow controller.

Renders interactive 3D digital twin of the MQTT process flow based on MQTT_PROCESS_FLOW.md.
Follows Clean Architecture: controllers do not contain business logic.
"""

from flask import Blueprint, render_template, request, session
from app.decorators import admin_required
from app.services.machine_telemetry_service import MachineTelemetryService


def register_admin_process_flow_routes(bp: Blueprint) -> None:
    """Register admin routes for the 3D process flow digital twin."""

    @bp.route('/admin/master/process-flow-3d', methods=['GET'])
    @admin_required
    def admin_master_process_flow_3d():
        """Render the 3D Digital Twin process flow view."""
        initial_telemetry = MachineTelemetryService.get_live_dashboard_data()
        current_hall = (
            request.args.get('linia')
            or session.get('selected_hall_view')
            or session.get('grupa')
            or 'AGRO'
        )

        return render_template(
            'admin/process_flow_3d.html',
            initial_telemetry=initial_telemetry,
            linia=current_hall,
        )
