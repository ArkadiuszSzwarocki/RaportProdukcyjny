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
    @main_bp.route('/raport/zakoncz_zmiane', methods=['GET'])
    @login_required
    @roles_required('lider', 'admin', 'masteradmin', 'zarzad')
    def raport_zakoncz_zmiane_page():
        """Strona podsumowania i wysyłki raportu e-mail przy zakończeniu zmiany."""
        from datetime import date, datetime
        from app.services.shift_close_service import _load_shift_notes, _get_leader_name, _generate_report_files
        from app.services.email_service import EmailService
        from app.services.email_report_builder import EmailReportBuilder
        from app.repositories.user_email_settings_repository import UserEmailSettingsRepository
        from app.repositories.downtime_repository import DowntimeRepository
        from app.db import get_db_connection, get_table_name
        import pandas as pd
        from flask import render_template

        linia = (request.args.get('linia') or session.get('selected_hall_view') or 'PSD').strip().upper()
        date_str = request.args.get('data') or str(date.today())
        
        session_data = {
            'pracownik_id': session.get('pracownik_id'),
            'login': session.get('login', 'nieznany'),
            'imie_nazwisko': session.get('imie_nazwisko'),
            'rola': session.get('rola')
        }
        form_data = {
            'lider_id': request.args.get('lider_id') or None,
            'lider_prowadzacy_id': None
        }

        # 1. Notatki i lider
        uwagi = _load_shift_notes(date_str, linia=linia)
        lider_name, uwagi_extra = _get_leader_name(session_data, form_data, linia=linia, date_str=date_str)
        
        # 2. Wygeneruj pliki raportu (XLS, PDF)
        xls_path, _, pdf_path = _generate_report_files(date_str, uwagi + uwagi_extra, lider_name, linia=linia)

        # 3. Lista załączników z metadanymi
        attachments_info = []
        for p, label, icon in [
            (pdf_path, f"Raport_{linia}_{date_str}.pdf", "📄"),
            (xls_path, f"Raport_{linia}_{date_str}.xlsx", "📊"),
        ]:
            if p and os.path.exists(p):
                size_kb = round(os.path.getsize(p) / 1024, 1)
                attachments_info.append({
                    'path': str(p),
                    'filename': os.path.basename(p),
                    'label': label,
                    'icon': icon,
                    'size_kb': size_kb,
                    'exists': True
                })

        # 4. Pobierz szczegóły produkcji (Zasyp, Workowanie)
        suma_zasyp = 0
        suma_workowanie = 0
        palety_count = 0
        suma_laczna = 0
        try:
            conn = get_db_connection()
            table_plan = get_table_name('plan_produkcji', linia)
            table_palety = get_table_name('palety_workowanie', linia)
            table_szarze = 'szarze_agro' if linia == 'AGRO' else 'szarze'
            c_prod = conn.cursor(dictionary=True)

            # 1. Zasyp wykonany w danym dniu
            try:
                c_prod.execute(f"SELECT COALESCE(SUM(waga), 0) as s FROM {table_szarze} WHERE DATE(data_dodania) = %s", (date_str,))
                r_z = c_prod.fetchone()
                suma_zasyp = int(r_z['s']) if r_z and r_z['s'] else 0
            except Exception:
                suma_zasyp = 0

            if suma_zasyp == 0:
                try:
                    c_prod.execute(f"SELECT COALESCE(SUM(tonaz_rzeczywisty), 0) as s FROM {table_plan} WHERE data_planu = %s AND LOWER(sekcja) = 'zasyp'", (date_str,))
                    r_z2 = c_prod.fetchone()
                    suma_zasyp = int(r_z2['s']) if r_z2 and r_z2['s'] else 0
                except Exception:
                    pass

            # 2. Workowanie - bezpośrednio z palet spakowanych w danym dniu!
            try:
                c_prod.execute(f"SELECT COUNT(id) as cnt, COALESCE(SUM(waga), 0) as s FROM {table_palety} WHERE DATE(data_dodania) = %s", (date_str,))
                r_w = c_prod.fetchone()
                if r_w:
                    palety_count = int(r_w['cnt'] or 0)
                    suma_workowanie = int(r_w['s'] or 0)
            except Exception as w_err:
                current_app.logger.warning("Błąd pobierania palet workowania: %s", w_err)

            suma_laczna = suma_zasyp + suma_workowanie
            c_prod.close()
            conn.close()
        except Exception as e:
            current_app.logger.warning("Błąd wyliczania tonazu w reporting: %s", e)

        # 5. Pobierz przestoje
        downtimes = []
        total_downtime_min = 0
        try:
            downtimes = DowntimeRepository().get_downtimes(linia, date_str, date_str)
            for dt in downtimes:
                dur = dt.get('czas_trwania_min')
                if dur is None and dt.get('godzina_start') and dt.get('godzina_stop'):
                    try:
                        t1 = datetime.strptime(str(dt['godzina_start'])[:5], '%H:%M')
                        t2 = datetime.strptime(str(dt['godzina_stop'])[:5], '%H:%M')
                        diff = int((t2 - t1).total_seconds() / 60)
                        if diff < 0:
                            diff += 1440
                        dur = diff
                    except Exception:
                        dur = 0
                dur_val = int(dur or 0)
                total_downtime_min += dur_val
        except Exception as e:
            current_app.logger.warning("Błąd pobierania przestojów: %s", e)

        # 6. Odczytaj proponowaną treść notatek
        initial_notes_text = uwagi.strip() if uwagi else ""

        # 7. Zbuduj podgląd HTML
        att_filenames = [a['filename'] for a in attachments_info]
        email_preview_html = EmailReportBuilder.build_shift_report_html(
            linia=linia,
            date_str=date_str,
            lider_name=lider_name,
            suma_zasyp=suma_zasyp,
            suma_workowanie=suma_workowanie,
            downtimes=downtimes,
            total_downtime_min=total_downtime_min,
            notes_text=initial_notes_text,
            attachments_names=att_filenames,
            palety_count=palety_count
        )

        # 8. Konfiguracja konta SMTP nadawcy i odbiorców
        email_service = EmailService()
        user_id = session.get('user_id')
        smtp_config = email_service.get_smtp_config_for_user(user_id)
        all_recipients = []
        domyslni_odbiorcy = ""
        try:
            email_repo = UserEmailSettingsRepository()
            # Pobieraj wyłącznie aktywnych odbiorców ze słownika
            all_recipients = email_repo.get_all_recipients(only_active=True)
            active_emails = [r['email'].strip().lower() for r in all_recipients if r.get('email')]

            user_settings = email_repo.get_by_user_id(user_id) if user_id else None
            if user_settings and user_settings.domyslni_odbiorcy:
                # Odfiltruj odbiorców, którzy zostali wyłączeni/wstrzymani w słowniku
                saved_emails = [e.strip() for e in user_settings.domyslni_odbiorcy.replace(';', ',').split(',') if e.strip()]
                if active_emails:
                    filtered_saved = [e for e in saved_emails if e.lower() in active_emails]
                    domyslni_odbiorcy = ", ".join(filtered_saved) if filtered_saved else ", ".join([r['email'] for r in all_recipients])
                else:
                    domyslni_odbiorcy = ", ".join(saved_emails)
            else:
                domyslni_odbiorcy = ", ".join([r['email'] for r in all_recipients])
        except Exception as e:
            current_app.logger.warning("Błąd pobierania odbiorców: %s", e)

        # Sprawdzenie czy raport dotyczy prac po zakończeniu I zmiany
        from app.services.auto_report_service import AutoReportService
        has_post_1500 = AutoReportService.has_activity_after_1500(linia, date_str)
        is_sent_1500 = AutoReportService.is_1500_report_sent(linia, date_str)
        sched = AutoReportService.get_schedule(linia, date_str)
        sched_time_str = sched.get('scheduled_time', '15:00')

        # Domyślny temat: nowo zdefiniowana godzina to nadal I zmiana (jeden raport)
        if is_sent_1500 and has_post_1500:
            domyslny_temat = f"Raport Produkcyjny {linia} — Praca po {sched_time_str} / II Zmiana — {date_str}"
        else:
            domyslny_temat = f"Raport Produkcyjny {linia} — Zmiana z dnia {date_str}"

        return render_template(
            'raport_zakoncz_zmiane_email.html',
            linia=linia,
            date_str=date_str,
            lider_name=lider_name,
            attachments_info=attachments_info,
            initial_notes_text=initial_notes_text,
            email_preview_html=email_preview_html,
            suma_zasyp=suma_zasyp,
            suma_workowanie=suma_workowanie,
            downtimes=downtimes,
            total_downtime_min=total_downtime_min,
            domyslny_temat=domyslny_temat,
            smtp_config=smtp_config,
            all_recipients=all_recipients,
            domyslni_odbiorcy=domyslni_odbiorcy,
            has_post_1500=has_post_1500,
            is_sent_1500=is_sent_1500
        )

    @main_bp.route('/raport/zakoncz_zmiane/wyslij', methods=['POST'])
    @login_required
    @roles_required('lider', 'admin', 'masteradmin', 'zarzad')
    def raport_zakoncz_zmiane_wyslij():
        """Wysyła e-mail z raportem i zamyka zmianę."""
        from datetime import date
        from app.services.email_service import EmailService
        from app.services.email_report_builder import EmailReportBuilder
        from app.repositories.user_email_settings_repository import UserEmailSettingsRepository
        from app.repositories.downtime_repository import DowntimeRepository
        from app.db import get_db_connection, get_table_name
        from app.core.audit import audit_log
        import pandas as pd

        data = request.form
        linia = (data.get('linia') or request.args.get('linia') or session.get('selected_hall_view') or 'PSD').strip().upper()
        date_str = data.get('date_str') or str(date.today())
        raw_to = data.get('to_emails') or ''
        subject = (data.get('subject') or f"Raport Produkcyjny {linia} - {date_str}").strip()
        notes_text = data.get('notes_text') or data.get('body_text') or ''
        close_shift_flag = data.get('close_shift') == '1'
        save_recipients = data.get('save_recipients') == '1'

        to_emails = [e.strip() for e in raw_to.replace(';', ',').split(',') if e.strip()]
        if not to_emails:
            flash("❌ Musisz podać co najmniej jeden adres e-mail odbiorcy.", "danger")
            return redirect(url_for('main.raport_zakoncz_zmiane_page', linia=linia, data=date_str))

        from app.services.auto_report_service import AutoReportService
        if not AutoReportService.has_report_data(linia, date_str):
            flash("⚠️ Raport dla wybranej linii i daty nie zawiera żadnych danych produkcyjnych ani przestojów. Wysyłka została anulowana.", "warning")
            return redirect(url_for('main.raport_zakoncz_zmiane_page', linia=linia, data=date_str))

        # Załączniki zaznaczone przez użytkownika
        selected_attachments = request.form.getlist('attachments')
        valid_attachments = [p for p in selected_attachments if os.path.exists(p)]
        att_filenames = [os.path.basename(p) for p in valid_attachments]

        # Pobierz aktualne dane produkcji (zasyp i workowanie) wykonane dokładnie w danym dniu
        suma_zasyp = 0
        suma_workowanie = 0
        palety_count = 0
        try:
            conn = get_db_connection()
            table_plan = get_table_name('plan_produkcji', linia)
            table_szarze = 'szarze_agro' if linia == 'AGRO' else 'szarze'
            table_palety = get_table_name('palety_workowanie', linia)
            c_prod = conn.cursor(dictionary=True)
            try:
                c_prod.execute(f"SELECT COALESCE(SUM(waga), 0) as s FROM {table_szarze} WHERE DATE(data_dodania) = %s", (date_str,))
                r_z = c_prod.fetchone()
                suma_zasyp = int(r_z['s']) if r_z and r_z['s'] else 0
            except Exception:
                suma_zasyp = 0

            if suma_zasyp == 0:
                try:
                    c_prod.execute(f"SELECT COALESCE(SUM(tonaz_rzeczywisty), 0) as s FROM {table_plan} WHERE data_planu = %s AND LOWER(sekcja) = 'zasyp'", (date_str,))
                    r_z2 = c_prod.fetchone()
                    suma_zasyp = int(r_z2['s']) if r_z2 and r_z2['s'] else 0
                except Exception:
                    pass

            try:
                c_prod.execute(f"SELECT COUNT(id) as cnt, COALESCE(SUM(waga), 0) as s FROM {table_palety} WHERE DATE(data_dodania) = %s", (date_str,))
                r_w = c_prod.fetchone()
                if r_w:
                    palety_count = int(r_w['cnt'] or 0)
                    suma_workowanie = int(r_w['s'] or 0)
            except Exception as w_err:
                current_app.logger.warning("Błąd pobierania palet workowania w email: %s", w_err)

            c_prod.close()
            conn.close()
        except Exception:
            pass

        downtimes = []
        total_downtime_min = 0
        try:
            downtimes = DowntimeRepository().get_downtimes(linia, date_str, date_str)
            for dt in downtimes:
                dur = dt.get('czas_trwania_min')
                if dur is None and dt.get('godzina_start') and dt.get('godzina_stop'):
                    try:
                        t1 = datetime.strptime(str(dt['godzina_start'])[:5], '%H:%M')
                        t2 = datetime.strptime(str(dt['godzina_stop'])[:5], '%H:%M')
                        diff = int((t2 - t1).total_seconds() / 60)
                        if diff < 0:
                            diff += 1440
                        dur = diff
                    except Exception:
                        dur = 0
                dur_val = int(dur or 0)
                total_downtime_min += dur_val
        except Exception:
            pass

        from app.services.shift_close_service import _get_leader_name
        session_data = {
            'pracownik_id': session.get('pracownik_id'),
            'login': session.get('login', 'nieznany'),
            'imie_nazwisko': session.get('imie_nazwisko'),
            'rola': session.get('rola')
        }
        lider_name, _ = _get_leader_name(session_data, {}, linia=linia, date_str=date_str)

        # Zbuduj bogaty graficzny szablon HTML
        body_html = EmailReportBuilder.build_shift_report_html(
            linia=linia,
            date_str=date_str,
            lider_name=lider_name,
            suma_zasyp=suma_zasyp,
            suma_workowanie=suma_workowanie,
            downtimes=downtimes,
            total_downtime_min=total_downtime_min,
            notes_text=notes_text,
            attachments_names=att_filenames,
            palety_count=palety_count
        )

        user_id = session.get('user_id')
        email_service = EmailService()
        success, message = email_service.send_report_email(
            to_emails=to_emails,
            subject=subject,
            body_html=body_html,
            attachments=valid_attachments,
            user_id=user_id
        )

        if not success:
            flash(f"❌ {message}", "danger")
            return redirect(url_for('main.raport_zakoncz_zmiane_page', linia=linia, data=date_str))

        # Opcjonalny zapis odbiorców jako domyślnych
        if save_recipients and user_id:
            try:
                settings_repo = UserEmailSettingsRepository()
                user_conf = settings_repo.get_by_user_id(user_id)
                if user_conf:
                    settings_repo.save_or_update(
                        user_id=user_id,
                        smtp_server=user_conf.smtp_server,
                        smtp_port=user_conf.smtp_port,
                        smtp_security=user_conf.smtp_security,
                        smtp_username=user_conf.smtp_username,
                        smtp_password=user_conf.smtp_password,
                        sender_name=user_conf.sender_name,
                        domyslni_odbiorcy=",".join(to_emails)
                    )
            except Exception as e:
                current_app.logger.warning("Nie udało się zapisać domyślnych odbiorców: %s", e)

        # Jeśli zaznaczono zamknięcie zmiany
        if close_shift_flag:
            try:
                from app.services.shift_close_service import _suspend_previous_day_plans
                _suspend_previous_day_plans(date_str, linia=linia)
                audit_log('Zakończono zmianę i wysłano raport', f'Linia={linia}, Data={date_str}, Odbiorcy={", ".join(to_emails)}')
            except Exception as e:
                current_app.logger.error("Błąd zamykania planów: %s", e)

        flash(f"✅ Raport został pomyślnie wysłany na podane adresy e-mail ({len(to_emails)} odbiorców)! Zmiana została pomyślnie zapisana.", "success")
        return redirect(url_for('main.index', linia=linia))

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

        hala = (request.form.get('hala') or request.form.get('linia') or 'PSD').strip().upper()
        sekcja = (request.form.get('sekcja') or 'Workowanie').strip()
        kategoria = (request.form.get('kategoria') or 'Awaria').strip()
        godzina_start = (request.form.get('godzina_start') or datetime.now().strftime('%H:%M')).strip()
        godzina_stop = (request.form.get('godzina_stop') or '').strip() or None

        czas_trwania_min = None
        if godzina_start and godzina_stop:
            try:
                t1 = datetime.strptime(godzina_start[:5], '%H:%M')
                t2 = datetime.strptime(godzina_stop[:5], '%H:%M')
                diff = int((t2 - t1).total_seconds() / 60)
                if diff < 0:
                    diff += 1440
                czas_trwania_min = diff
            except Exception:
                czas_trwania_min = None

        header_prefix = f"[{hala} | {sekcja} | {kategoria}]"
        if godzina_start:
            header_prefix += f" ({godzina_start}" + (f" - {godzina_stop}" if godzina_stop else "") + ")"
        
        full_opis = f"{header_prefix}\n{opis}"
        if gdzie:
            full_opis = f"[Miejsce] {gdzie}\n{full_opis}"

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

        # 1. Zapis do zgłoszeń błędów / DUR
        conn = db.get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO zgloszenia_bledow (id, timestamp, login, opis, sciezka, zalaczniki, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (report_id, datetime.now(), login, full_opis, sciezka, json.dumps(saved_files), 'nowy'),
            )
            conn.commit()
        except Exception as error:
            current_app.logger.error('Błąd zapisu zgłoszenia do bazy: %s', error)
            return jsonify({'success': False, 'message': 'Błąd zapisu zgłoszenia'}), 500
        finally:
            conn.close()

        # 2. Zgłoszenia z formularza "Robaczek" (błędy systemu / IT / usterki) NIE trafiają do raportu produkcyjnego PSD.
        # Jedynie opcjonalnie dla AGRO, jeśli wyraźnie wskazano tę halę w dedykowanym formularzu awarii.
        if hala == 'AGRO' and request.form.get('hala'):
            try:
                from app.repositories.downtime_repository import DowntimeRepository
                downtime_repo = DowntimeRepository()
                target_sekcja = 'Zasyp' if 'zasyp' in sekcja.lower() else 'Workowanie'
                zdjecie_url = f"/static/uploads/bugs/{saved_files[0]}" if saved_files else None
                data_przestoju = datetime.now().strftime('%Y-%m-%d')

                downtime_repo.insert_downtime(
                    linia=hala,
                    sekcja=target_sekcja,
                    plan_id=None,
                    produkt=None,
                    data_przestoju=data_przestoju,
                    godzina_start=godzina_start,
                    godzina_stop=godzina_stop,
                    czas_trwania_min=czas_trwania_min,
                    kategoria=kategoria,
                    opis=opis,
                    zglaszajacy=login,
                    zdjecie_url=zdjecie_url
                )
                current_app.logger.info("Pomyślnie dodano awarię do rejestru przestojów hali %s (%s)", hala, target_sekcja)
            except Exception as dt_err:
                current_app.logger.warning("Błąd zapisu awarii do tabel przestojów: %s", dt_err)

        return jsonify({'success': True, 'message': f'Zgłoszenie awarii dla hali {hala} zostało zapisane.'})

    @main_bp.route('/raport/podglad_pdf')
    @login_required
    def raport_podglad_pdf():
        """Strona podglądu pełnego raportu PDF w tym samym oknie aplikacji."""
        from datetime import date
        from flask import render_template
        from app.services.shift_close_service import _get_leader_name

        linia = (request.args.get('linia') or 'AGRO').strip().upper()
        date_str = request.args.get('data') or str(date.today())

        session_data = {
            'pracownik_id': session.get('pracownik_id'),
            'login': session.get('login', 'nieznany'),
            'imie_nazwisko': session.get('imie_nazwisko')
        }
        form_data = {
            'lider_id': session.get('pracownik_id'),
            'lider_prowadzacy_id': None
        }

        lider_name, _ = _get_leader_name(session_data, form_data)

        return render_template(
            'raport_podglad_pdf_page.html',
            linia=linia,
            date_str=date_str,
            lider_name=lider_name
        )

    @main_bp.route('/raport/podglad_pdf/stream')
    @login_required
    def raport_podglad_pdf_stream():
        """Strumieniuje wygenerowany plik PDF do osadzonej ramki w przeglądarce."""
        from datetime import date
        from flask import send_file
        from app.services.shift_close_service import _load_shift_notes, _get_leader_name, _generate_report_files

        linia = (request.args.get('linia') or 'AGRO').strip().upper()
        date_str = request.args.get('data') or str(date.today())

        session_data = {
            'pracownik_id': session.get('pracownik_id'),
            'login': session.get('login', 'nieznany'),
            'imie_nazwisko': session.get('imie_nazwisko')
        }
        form_data = {
            'lider_id': session.get('pracownik_id'),
            'lider_prowadzacy_id': None
        }

        uwagi = _load_shift_notes(date_str, linia=linia)
        lider_name, uwagi_extra = _get_leader_name(session_data, form_data)
        
        _, _, pdf_path = _generate_report_files(date_str, uwagi + uwagi_extra, lider_name, linia=linia)

        if pdf_path and os.path.exists(pdf_path):
            return send_file(
                pdf_path,
                mimetype='application/pdf',
                as_attachment=False,
                download_name=f"Raport_{linia}_{date_str}.pdf"
            )
        
        return "Błąd: Nie znaleziono pliku PDF.", 404

    @main_bp.route('/raport/pobierz_pdf')
    @login_required
    def raport_pobierz_pdf_file():
        """Pobiera plik raportu PDF na dysk użytkownika."""
        from datetime import date
        from flask import send_file
        from app.services.shift_close_service import _load_shift_notes, _get_leader_name, _generate_report_files

        linia = (request.args.get('linia') or 'AGRO').strip().upper()
        date_str = request.args.get('data') or str(date.today())

        session_data = {
            'pracownik_id': session.get('pracownik_id'),
            'login': session.get('login', 'nieznany'),
            'imie_nazwisko': session.get('imie_nazwisko')
        }
        form_data = {
            'lider_id': session.get('pracownik_id'),
            'lider_prowadzacy_id': None
        }

        uwagi = _load_shift_notes(date_str, linia=linia)
        lider_name, uwagi_extra = _get_leader_name(session_data, form_data)
        
        _, _, pdf_path = _generate_report_files(date_str, uwagi + uwagi_extra, lider_name, linia=linia)

        if pdf_path and os.path.exists(pdf_path):
            return send_file(
                pdf_path,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=f"Raport_{linia}_{date_str}.pdf"
            )
        
        flash("❌ Nie udało się pobrać pliku PDF.", "danger")
        return redirect(url_for('main.index', linia=linia))

    @main_bp.route('/api/auto_raport/status', methods=['GET'])
    @login_required
    def api_auto_raport_status():
        """Zwraca aktualny status, konfigurację i godzinę zaplanowanego auto-raportu."""
        from datetime import date
        from app.services.auto_report_service import AutoReportService

        linia = (request.args.get('linia') or 'AGRO').strip().upper()
        date_str = request.args.get('data') or str(date.today())

        sched = AutoReportService.get_schedule(linia, date_str)
        is_sent = AutoReportService.is_1500_report_sent(linia, date_str)
        has_post = AutoReportService.has_activity_after_1500(linia, date_str)
        config = AutoReportService.get_global_config()

        return jsonify({
            'success': True,
            'schedule': sched,
            'is_sent': is_sent,
            'has_post_1500': has_post,
            'config': config
        })

    @main_bp.route('/api/auto_raport/config', methods=['GET', 'POST'])
    @login_required
    def api_auto_raport_config():
        """Pobiera lub zapisuje globalną konfigurację automatycznego raportowania (dni i linie)."""
        from app.services.auto_report_service import AutoReportService

        if request.method == 'GET':
            return jsonify({
                'success': True,
                'config': AutoReportService.get_global_config()
            })

        # POST - tylko dla ról uprawnionych
        role = session.get('rola')
        if role not in ['lider', 'admin', 'masteradmin', 'zarzad']:
            return jsonify({'success': False, 'message': 'Brak uprawnień do zmiany konfiguracji.'}), 403

        payload = request.get_json(silent=True) or request.form
        active_days = payload.get('active_days')
        if active_days is None:
            active_days = [0, 1, 2, 3, 4]
        elif isinstance(active_days, str):
            active_days = [int(d.strip()) for d in active_days.split(',') if d.strip().isdigit()]

        enabled_lines = payload.get('enabled_lines')
        if enabled_lines is None:
            enabled_lines = ['AGRO', 'PSD']
        elif isinstance(enabled_lines, str):
            enabled_lines = [l.strip().upper() for l in enabled_lines.split(',') if l.strip()]

        user_name = session.get('imie_nazwisko') or session.get('login') or 'Lider'

        ok, msg = AutoReportService.save_global_config(
            active_days=active_days,
            enabled_lines=enabled_lines,
            user_name=user_name
        )

        return jsonify({
            'success': ok,
            'message': msg,
            'config': AutoReportService.get_global_config()
        })

    @main_bp.route('/api/auto_raport/odloz', methods=['POST'])
    @login_required
    @roles_required('lider', 'admin', 'masteradmin', 'zarzad')
    def api_auto_raport_odloz():
        """Odracza lub zmienia czas wysyłki automatycznego raportu."""
        from datetime import date
        from app.services.auto_report_service import AutoReportService

        payload = request.get_json(silent=True) or request.form
        linia = (payload.get('linia') or 'AGRO').strip().upper()
        date_str = payload.get('data') or str(date.today())
        add_minutes = payload.get('add_minutes')
        new_time = payload.get('new_time')
        pause_completely = str(payload.get('pause_completely', '')).lower() in ['true', '1', 'yes']
        reset_to_default = str(payload.get('reset_to_default', '')).lower() in ['true', '1', 'yes']

        user_name = session.get('imie_nazwisko') or session.get('login') or 'Lider'

        ok, msg, sched = AutoReportService.postpone_report(
            linia=linia,
            date_str=date_str,
            add_minutes=int(add_minutes) if add_minutes else None,
            new_time=new_time,
            pause_completely=pause_completely,
            reset_to_default=reset_to_default,
            user_name=user_name
        )

        return jsonify({
            'success': ok,
            'message': msg,
            'schedule': sched
        })

    @main_bp.route('/zamknij_zmiane', methods=['GET', 'POST'])
    def legacy_zamknij_zmiane():
        if request.method == 'GET':
            return redirect('/')
        if not session.get('user_id') and not session.get('login') and not session.get('pracownik_id'):
            return redirect('/login')
        role = str(session.get('rola', '')).lower().strip()
        if role not in ['lider', 'admin', 'masteradmin', 'zarzad']:
            return jsonify({'error': 'Brak uprawnień'}), 403

        try:
            conn = get_db_connection()
            if conn:
                try:
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1")
                except Exception:
                    pass
        except Exception:
            pass

        return redirect('/')

    @main_bp.route('/wyslij_raport_email', methods=['POST'])
    def legacy_wyslij_raport_email():
        if not session.get('user_id') and not session.get('login') and not session.get('pracownik_id'):
            return redirect('/login')
        return redirect('/')