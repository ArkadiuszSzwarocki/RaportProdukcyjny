import json
import os
import time
from datetime import datetime
from typing import Tuple, Union

from flask import Response, current_app, flash, jsonify, redirect, request, send_file, session, url_for

from app import db
from app.decorators import login_required, roles_required
from app.services.report_generation_service import ReportGenerationService


def register_main_reporting_routes(main_bp):
    @main_bp.route('/zamknij_zmiane', methods=['GET'])
    @roles_required('lider', 'admin')
    def zamknij_zmiane_get() -> Response:
        """Redirect GET requests on shift close endpoint to index."""
        return redirect(url_for('main.index'))

    @main_bp.route('/zamknij_zmiane', methods=['POST'])
    @roles_required('lider', 'admin')
    def zamknij_zmiane() -> Union[Response, Tuple[str, int]]:
        """Close current shift and generate final reports."""
        uwagi_lidera = request.form.get('uwagi_lidera', '')
        aktywna_linia = request.form.get('linia', request.args.get('linia', 'PSD'))
        zip_path, mime_type = ReportGenerationService.close_shift_and_generate_reports(uwagi_lidera, linia=aktywna_linia)

        if zip_path:
            return send_file(zip_path, as_attachment=True, mimetype=mime_type)

        flash('⚠️ Nie udało się wygenerować raportu. Sprawdź logi serwera.', 'warning')
        return redirect(url_for('main.index'))

    @main_bp.route('/wyslij_raport_email', methods=['POST'])
    def wyslij_raport_email() -> Response:
        """Email a generated report placeholder."""
        return redirect(url_for('main.index'))

    @main_bp.route('/api/zglos_blad_systemu', methods=['POST'])
    @login_required
    def zglos_blad_systemu() -> Response:
        """Zgłoś błąd z możliwością uploadu do 3 zrzutów ekranu."""
        opis = (request.form.get('opis', '') or '').strip()
        gdzie = (request.form.get('gdzie', '') or '').strip()
        sciezka = request.form.get('sciezka', '')
        login = session.get('login', 'Nieznany')

        if not opis:
            return jsonify({'success': False, 'message': 'Opis problemu jest wymagany.'}), 400

        if gdzie:
            opis = f'[Miejsce występowania] {gdzie}\n\n{opis}'

        upload_dir = os.path.join(current_app.static_folder, 'uploads', 'bugs')
        os.makedirs(upload_dir, exist_ok=True)

        report_id = int(time.time() * 1000)
        saved_files = []

        files = request.files.getlist('zalaczniki')
        for index, file in enumerate(files[:3]):
            if not file or not file.filename:
                continue
            ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'png'
            if ext not in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
                continue
            filename = f'bug_{report_id}_{index}.{ext}'
            try:
                file.save(os.path.join(upload_dir, filename))
                saved_files.append(filename)
            except Exception as error:
                current_app.logger.warning('Błąd zapisu pliku: %s', error)

        conn = db.get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO zgloszenia_bledow (id, timestamp, login, opis, sciezka, zalaczniki, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (report_id, datetime.now(), login, opis, sciezka, json.dumps(saved_files), 'nowy'),
            )
            conn.commit()
        except Exception as error:
            current_app.logger.error('Błąd zapisu zgłoszenia do bazy: %s', error)
            return jsonify({'success': False, 'message': 'Błąd zapisu zgłoszenia'}), 500
        finally:
            conn.close()

        return jsonify({'success': True, 'message': 'Zgłoszenie zostało przyjęte.'})