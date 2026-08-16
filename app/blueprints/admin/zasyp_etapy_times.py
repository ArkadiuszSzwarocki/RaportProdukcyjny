import json
import os
import re
from flask import current_app, flash, redirect, render_template, request
from app.decorators import dynamic_role_required

def _candidate_config_paths():
    return [
        os.path.join(current_app.root_path, 'config', 'zasyp_etapy_times.json'),
        os.path.join(os.path.dirname(current_app.root_path), 'config', 'zasyp_etapy_times.json'),
        os.path.join(os.path.dirname(os.path.dirname(current_app.root_path)), 'config', 'zasyp_etapy_times.json'),
    ]

def _resolve_config_path():
    for config_path in _candidate_config_paths():
        try:
            if os.path.exists(config_path):
                return config_path
        except Exception:
            continue

    fallback_dir = os.path.abspath(os.path.join(os.path.dirname(current_app.root_path), 'config'))
    if not os.path.isdir(fallback_dir):
        fallback_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(current_app.root_path)), 'config'))
    
    if not os.path.isdir(fallback_dir):
        os.makedirs(fallback_dir, exist_ok=True)
    
    return os.path.join(fallback_dir, 'zasyp_etapy_times.json')

def _load_times_config():
    config_path = _resolve_config_path()
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            current_app.logger.error("Błąd podczas ładowania zasyp_etapy_times.json: %s", e)
    
    return {
        "nawazanie_min": 20,
        "mieszanie_min": 10,
        "dosypka_min": 5,
        "oproznianie_min": 10
    }

def register_admin_zasyp_etapy_times_routes(admin_bp):
    @admin_bp.route('/admin/ustawienia/zasyp_etapy_times', methods=['GET'])
    @dynamic_role_required('ustawienia')
    def admin_zasyp_etapy_times():
        """Wyświetl ustawienia widełek czasowych dla etapów (punktów kontrolnych)."""
        return render_template('ustawienia_zasyp_etapy_times.html', times_config=_load_times_config())

    @admin_bp.route('/admin/ustawienia/zasyp_etapy_times/update', methods=['POST'])
    @dynamic_role_required('ustawienia')
    def admin_zasyp_etapy_times_update():
        """Zaktualizuj czasy dla etapów zasypu."""
        try:
            nawazanie_min = int(request.form.get('nawazanie_min') or 20)
            mieszanie_min = int(request.form.get('mieszanie_min') or 10)
            dosypka_min = int(request.form.get('dosypka_min') or 5)
            oproznianie_min = int(request.form.get('oproznianie_min') or 10)
            
            config_data = {
                "nawazanie_min": nawazanie_min,
                "mieszanie_min": mieszanie_min,
                "dosypka_min": dosypka_min,
                "oproznianie_min": oproznianie_min
            }
            
            config_path = _resolve_config_path()
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=4, ensure_ascii=False)
                
            flash("Poprawnie zaktualizowano limity czasowe dla punktów kontrolnych.", "success")
        except Exception as e:
            current_app.logger.error("Błąd zapisu ustawień zasyp_etapy_times: %s", e)
            flash("Wystąpił błąd podczas zapisywania ustawień. Sprawdź logi serwera.", "danger")
            
        return redirect('/admin/ustawienia/zasyp_etapy_times')
