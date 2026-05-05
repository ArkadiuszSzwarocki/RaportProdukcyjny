import json
import os
import re
import shutil
from datetime import datetime

from flask import current_app, flash, redirect, render_template, request

from app.decorators import dynamic_role_required


def _candidate_config_paths():
    return [
        os.path.join(current_app.root_path, 'config', 'workowanie_processing_times.json'),
        os.path.join(os.path.dirname(current_app.root_path), 'config', 'workowanie_processing_times.json'),
        os.path.join(os.path.dirname(os.path.dirname(current_app.root_path)), 'config', 'workowanie_processing_times.json'),
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
    os.makedirs(fallback_dir, exist_ok=True)
    return os.path.join(fallback_dir, 'workowanie_processing_times.json')


def _load_times_config():
    for config_path in _candidate_config_paths():
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as file_handle:
                    current_app.logger.debug('Loaded workowanie_processing_times.json from %s', config_path)
                    return json.load(file_handle)
        except Exception as error:
            current_app.logger.debug('Failed to read %s: %s', config_path, error)

    current_app.logger.error('workowanie_processing_times.json not found in any expected location; using empty defaults')
    return {'processing_times_minutes': {}}


def register_admin_workowanie_times_routes(admin_bp):
    @admin_bp.route('/admin/ustawienia/workowanie_times', methods=['GET'])
    @dynamic_role_required('ustawienia')
    def admin_workowanie_times():
        """Wyświetl ustawienia czasów przetwarzania dla Workowania."""
        return render_template('ustawienia_workowanie_times.html', times_config=_load_times_config())

    @admin_bp.route('/admin/ustawienia/workowanie_times/update', methods=['POST'])
    @dynamic_role_required('ustawienia')
    def admin_workowanie_times_update():
        """Zaktualizuj czasy przetwarzania dla Workowania."""
        config_path = _resolve_config_path()

        try:
            times_config = {}
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as file_handle:
                    times_config = json.load(file_handle)

            if os.path.exists(config_path):
                backup_path = config_path + f'.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
                try:
                    shutil.copy2(config_path, backup_path)
                except Exception:
                    current_app.logger.debug('Could not create backup of %s', config_path)

            processing_times = times_config.get('processing_times_minutes', {})

            for key in list(processing_times.keys()):
                prefix = f'{key}_'
                time_minutes = request.form.get(f'{prefix}time_minutes', '').strip()
                description = request.form.get(f'{prefix}description', '').strip()
                name = request.form.get(f'{prefix}name', '').strip()
                weight_kg = request.form.get(f'{prefix}weight_kg', '').strip()

                if time_minutes:
                    try:
                        processing_times[key]['processing_time_minutes'] = int(time_minutes)
                    except ValueError:
                        pass

                if description:
                    processing_times[key]['description'] = description

                if name:
                    processing_times[key]['name'] = name

                if weight_kg:
                    try:
                        processing_times[key]['weight_kg'] = int(weight_kg)
                    except ValueError:
                        pass

            for key in list(processing_times.keys()):
                try:
                    if request.form.get(f'{key}_deleted') == '1':
                        processing_times.pop(key, None)
                except Exception:
                    continue

            for field_name in request.form.keys():
                match = re.match(r'(new_\d+)_(\w+)', field_name)
                if not match:
                    continue

                new_key = match.group(1)
                field_type = match.group(2)
                if new_key not in processing_times:
                    processing_times[new_key] = {
                        'name': '',
                        'weight_kg': 0,
                        'processing_time_minutes': 15,
                        'description': '',
                    }

                value = request.form.get(field_name, '').strip()
                if field_type == 'name':
                    processing_times[new_key]['name'] = value
                elif field_type == 'weight_kg':
                    try:
                        processing_times[new_key]['weight_kg'] = int(value) if value else 0
                    except ValueError:
                        pass
                elif field_type == 'time_minutes':
                    try:
                        processing_times[new_key]['processing_time_minutes'] = int(value) if value else 15
                    except ValueError:
                        pass
                elif field_type == 'description':
                    processing_times[new_key]['description'] = value

            times_config['processing_times_minutes'] = processing_times

            with open(config_path, 'w', encoding='utf-8') as file_handle:
                json.dump(times_config, file_handle, ensure_ascii=False, indent=2)

            current_app.logger.debug('Updated workowanie_processing_times.json')
            flash('✓ Czasy przetwarzania Workowania zostały zaktualizowane!', 'success')
        except Exception as error:
            current_app.logger.exception('Error updating workowanie_processing_times.json: %s', error)
            flash(f'❌ Błąd podczas zapisu: {error}', 'error')

        return redirect('/admin/ustawienia/workowanie_times')