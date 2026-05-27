import datetime
import os
import subprocess
import sys

from flask import abort, current_app, flash, redirect, send_from_directory, session, url_for

from app.decorators import dynamic_role_required


def _project_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def _backups_dir():
    return os.path.join(_project_root(), 'backups')


def register_admin_backup_routes(admin_bp):
    @admin_bp.route('/admin/ustawienia/backups/create', methods=['POST'])
    @dynamic_role_required('ustawienia')
    def admin_ustawienia_backups_create():
        script_path = os.path.join(_project_root(), 'scripts', 'backup_database.py')
        python_executable = sys.executable

        try:
            env = os.environ.copy()
            env['PYTHONPATH'] = _project_root()

            result = subprocess.run(
                [python_executable, script_path],
                capture_output=True,
                text=True,
                env=env,
                cwd=_project_root(),
            )

            if result.returncode == 0:
                flash('Kopia zapasowa została utworzona pomyślnie.', 'success')
                current_app.logger.info('[BACKUP] Ręczny backup wykonany pomyślnie przez %s', session.get('login'))
            else:
                flash(f'Błąd podczas tworzenia kopii: {result.stderr}', 'danger')
                current_app.logger.error('[BACKUP] Błąd ręcznego backupu: %s', result.stderr)
        except Exception as error:
            flash(f'Wystąpił błąd krytyczny: {str(error)}', 'danger')
            current_app.logger.exception('[BACKUP] Wyjątek podczas ręcznego backupu: %s', error)

        return redirect(url_for('admin.admin_ustawienia_backups'))

    @admin_bp.route('/admin/ustawienia/backups')
    @dynamic_role_required('ustawienia')
    def admin_ustawienia_backups():
        files = []
        try:
            if os.path.exists(_backups_dir()):
                for name in os.listdir(_backups_dir()):
                    if not name.startswith('db-backup-'):
                        continue
                    full_path = os.path.join(_backups_dir(), name)
                    if os.path.isfile(full_path):
                        stat = os.stat(full_path)
                        files.append(
                            {
                                'name': name,
                                'size': stat.st_size,
                                'mtime': datetime.datetime.fromtimestamp(stat.st_mtime),
                            }
                        )
            files.sort(key=lambda item: item['mtime'], reverse=True)
        except Exception:
            files = []

        from flask import render_template

        return render_template('ustawienia_backups.html', backups=files)

    @admin_bp.route('/admin/ustawienia/backups/download/<path:filename>')
    @dynamic_role_required('ustawienia')
    def admin_ustawienia_backups_download(filename):
        requested = os.path.normpath(os.path.join(_backups_dir(), filename))
        if not requested.startswith(os.path.normpath(_backups_dir()) + os.sep):
            abort(404)
        if not os.path.exists(requested) or not os.path.isfile(requested):
            abort(404)
        return send_from_directory(_backups_dir(), filename, as_attachment=True)