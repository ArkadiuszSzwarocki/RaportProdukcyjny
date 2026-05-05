import json
import os
from datetime import date as date_type
from typing import Dict, Tuple

from flask import current_app, jsonify, render_template, request

from app.decorators import login_required, roles_required
from app.services.dashboard_service import DashboardService


DEFAULT_LAYOUTS = {
    'Zasyp': {
        'version': '1.0',
        'layout': {
            'header': {'enabled': True, 'order': 1, 'fontSize': '21px', 'padding': '20px', 'gap': '20px', 'description': 'Tytuł sekcji i info'},
            'stats': {'enabled': True, 'order': 2, 'fontSize': '16px', 'padding': '12px', 'gap': '12px', 'description': 'Plan, Wykonanie, % Realizacja'},
            'table': {
                'enabled': True,
                'order': 3,
                'fontSize': '14px',
                'padding': '10px',
                'columns': [
                    {'name': 'Produkt', 'visible': True, 'width': 'auto'},
                    {'name': 'Waga Planu', 'visible': True, 'width': 'auto'},
                    {'name': 'Wykonanie', 'visible': True, 'width': 'auto'},
                    {'name': 'Status', 'visible': True, 'width': 'auto'},
                    {'name': 'Zasypy', 'visible': True, 'width': 'auto'},
                    {'name': 'Akcje', 'visible': True, 'width': 'auto'},
                ],
                'description': 'Tabela planów produkcji',
            },
            'details': {'enabled': True, 'order': 4, 'fontSize': '12px', 'padding': '10px', 'description': 'Szczegóły palety/zasypu'},
        },
    },
    'Workowanie': {
        'version': '1.0',
        'layout': {
            'header': {'enabled': True, 'order': 1, 'fontSize': '21px', 'padding': '20px', 'description': 'Tytuł sekcji'},
            'stats': {'enabled': True, 'order': 2, 'fontSize': '16px', 'padding': '12px', 'description': 'Statystyki'},
            'table': {
                'enabled': True,
                'order': 3,
                'fontSize': '14px',
                'padding': '10px',
                'columns': [
                    {'name': 'Produkt', 'visible': True, 'width': 'auto'},
                    {'name': 'Waga', 'visible': True, 'width': 'auto'},
                    {'name': 'Status', 'visible': True, 'width': 'auto'},
                    {'name': 'Palety', 'visible': True, 'width': 'auto'},
                    {'name': 'Akcje', 'visible': True, 'width': 'auto'},
                ],
                'description': 'Tabela planów',
            },
        },
    },
}


def _layouts_config_path() -> str:
    return os.path.join(current_app.root_path, '../config/layouts.json')


def register_main_layout_routes(main_bp):
    @main_bp.route('/layout-editor')
    @login_required
    @roles_required('admin', 'lider')
    def layout_editor() -> str:
        """Visual layout editor for production sections."""
        return render_template('layout_editor.html')

    @main_bp.route('/sekcja/<name>/edit')
    @login_required
    @roles_required('admin', 'lider')
    def edit_layout(name: str) -> str:
        """Visual layout editor for section."""
        valid_sections = ['Zasyp', 'Workowanie', 'Magazyn']
        if name not in valid_sections:
            return ('<h2>Nieznana sekcja: %s</h2><a href="/">Wróć do dashboard</a>' % name, 404)

        layouts_config = {}
        try:
            config_path = _layouts_config_path()
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as file_handle:
                    layouts_config = json.load(file_handle)
                    current_app.logger.info('[EDIT-LAYOUT] Wczytano konfigurację z %s', config_path)
            else:
                current_app.logger.warning('[EDIT-LAYOUT] Plik %s nie istnieje, używam domyślnej konfiguracji', config_path)
        except Exception as error:
            current_app.logger.error('[EDIT-LAYOUT] Błąd wczytywania config/layouts.json: %s', error)

        if name not in layouts_config and name in DEFAULT_LAYOUTS:
            current_app.logger.info('[EDIT-LAYOUT] Sekcja %s nie znaleziona, używam domyślnej konfiguracji', name)
            layouts_config[name] = DEFAULT_LAYOUTS[name]

        layout = layouts_config.get(name, {'version': '1.0', 'layout': {}})
        return render_template(
            'layout_editor.html',
            sekcja=name,
            layout_config=json.dumps(layout),
            layout_data=layout,
            debug_mode=True,
        )

    @main_bp.route('/api/layout/get/<name>', methods=['GET'])
    @login_required
    def get_layout(name: str) -> Tuple[Dict, int]:
        """Get layout configuration for a section."""
        try:
            config_path = _layouts_config_path()
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as file_handle:
                    layouts_config = json.load(file_handle)
                if name in layouts_config:
                    return jsonify(layouts_config[name]), 200
            return jsonify({'version': '1.0', 'layout': {}}), 200
        except Exception as error:
            current_app.logger.exception('[GET-LAYOUT] Błąd wczytywania: %s', error)
            return jsonify({'version': '1.0', 'layout': {}}), 200

    @main_bp.route('/api/layout/save/<name>', methods=['POST'])
    @login_required
    @roles_required('admin', 'lider')
    def save_layout(name: str) -> Tuple[Dict, int]:
        """Save layout configuration."""
        try:
            data = request.get_json()
            layout_updates = data.get('layout', {})
            config_path = _layouts_config_path()

            layouts_config = {}
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as file_handle:
                    layouts_config = json.load(file_handle)

            if name not in layouts_config:
                layouts_config[name] = {'version': '1.0', 'layout': {}}

            layouts_config[name]['layout'].update(layout_updates)
            os.makedirs(os.path.dirname(config_path), exist_ok=True)

            with open(config_path, 'w', encoding='utf-8') as file_handle:
                json.dump(layouts_config, file_handle, indent=2, ensure_ascii=False)

            current_app.logger.info('[SAVE-LAYOUT] Zapisano layout dla %s', name)
            return jsonify({'status': 'ok', 'message': f'Layout dla {name} został zapisany'}), 200
        except Exception as error:
            current_app.logger.exception('[SAVE-LAYOUT] Błąd zapisu: %s', error)
            return jsonify({'status': 'error', 'message': str(error)}), 500

    @main_bp.route('/api/sekcja/dashboard-data', methods=['GET'])
    @login_required
    def api_get_section_data() -> Tuple[dict, int]:
        """Load production data for layout editor preview."""
        sekcja = request.args.get('sekcja', 'Zasyp')
        dzisiaj = date_type.today()

        try:
            linia = request.args.get('linia', 'PSD')
            plan_dnia, _palety_mapa, suma_plan, suma_wykonanie = DashboardService.get_production_plans(dzisiaj, sekcja, linia=linia)
            percent = int((suma_wykonanie / suma_plan * 100) if suma_plan > 0 else 0)

            items = []
            for plan in plan_dnia[:5]:
                items.append(
                    {
                        'product': plan[1] if len(plan) > 1 else 'N/A',
                        'plan': f"{plan[2] if len(plan) > 2 else 0} kg",
                        'status': plan[3] if len(plan) > 3 else 'zaplanowane',
                    }
                )

            return jsonify(
                {
                    'plan_total': f'{suma_plan:.0f} kg',
                    'execution_total': f'{suma_wykonanie:.0f} kg',
                    'percent_complete': percent,
                    'items': items,
                }
            ), 200
        except Exception as error:
            current_app.logger.exception('[API-SECTION-DATA] Błąd: %s', error)
            return jsonify({'plan_total': '0 kg', 'execution_total': '0 kg', 'percent_complete': 0, 'items': []}), 200