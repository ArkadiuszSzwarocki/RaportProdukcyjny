import json
import os

from flask import current_app, flash, redirect, render_template, request, session, url_for

from app.db import get_db_connection
from app.decorators import dynamic_role_required, login_required, masteradmin_required


def register_admin_bug_routes(admin_bp, *, create_notification):
    def _ensure_replies_table(cursor):
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS zgloszenia_bledow_odpowiedzi (
                id INT AUTO_INCREMENT PRIMARY KEY,
                zgloszenie_id BIGINT NOT NULL,
                autor_login VARCHAR(50) NOT NULL,
                tresc TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_zgloszenie_id (zgloszenie_id)
            )
        """)
        try:
            cursor.execute("""
                INSERT INTO zgloszenia_bledow_odpowiedzi (zgloszenie_id, autor_login, tresc, created_at)
                SELECT b.id, COALESCE(b.odpowiedz_by_login, 'admin'), b.odpowiedz_admina, COALESCE(b.odpowiedz_timestamp, b.timestamp)
                FROM zgloszenia_bledow b
                WHERE b.odpowiedz_admina IS NOT NULL AND TRIM(b.odpowiedz_admina) <> ''
                  AND NOT EXISTS (
                      SELECT 1 FROM zgloszenia_bledow_odpowiedzi r WHERE r.zgloszenie_id = b.id AND r.tresc = b.odpowiedz_admina
                  )
            """)
        except Exception:
            pass

    @admin_bp.route('/admin/ustawienia/bugs')
    @login_required
    @dynamic_role_required('ustawienia')
    def admin_ustawienia_bugs():
        """View manually reported bugs from database with full reply history."""
        sort_by = request.args.get('sort', 'id_desc')
        filter_by = request.args.get('filter', 'all')
        
        # Map sort param to SQL
        sort_map = {
            'id_desc': 'id DESC',
            'id_asc': 'id ASC',
            'date_desc': 'timestamp DESC',
            'date_asc': 'timestamp ASC',
            'status': 'status ASC, timestamp DESC',
            'user': 'login ASC, timestamp DESC',
            'reply_date': 'odpowiedz_timestamp DESC'
        }
        order_clause = sort_map.get(sort_by, 'id DESC')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            _ensure_replies_table(cursor)
            cursor.execute(f'SELECT * FROM zgloszenia_bledow ORDER BY {order_clause}')
            bugs = cursor.fetchall() or []

            # Pobierz wszystkie odpowiedzi z tabeli dedykowanej
            cursor.execute('SELECT * FROM zgloszenia_bledow_odpowiedzi ORDER BY created_at ASC, id ASC')
            all_replies = cursor.fetchall() or []
            
            replies_by_bug = {}
            for rep in all_replies:
                b_id = rep['zgloszenie_id']
                if b_id not in replies_by_bug:
                    replies_by_bug[b_id] = []
                replies_by_bug[b_id].append(rep)

            for bug in bugs:
                if isinstance(bug.get('zalaczniki'), str):
                    try:
                        bug['zalaczniki'] = json.loads(bug['zalaczniki'])
                    except Exception:
                        bug['zalaczniki'] = []
                elif not bug.get('zalaczniki'):
                    bug['zalaczniki'] = []

                # Połącz odpowiedzi z nowej tabeli lub użyj legacy odpowiedz_admina
                bug_replies = replies_by_bug.get(bug['id'], [])
                if not bug_replies and bug.get('odpowiedz_admina'):
                    bug_replies = [{
                        'id': 0,
                        'zgloszenie_id': bug['id'],
                        'autor_login': bug.get('odpowiedz_by_login') or 'admin',
                        'tresc': bug.get('odpowiedz_admina'),
                        'created_at': bug.get('odpowiedz_timestamp') or bug.get('timestamp')
                    }]
                bug['odpowiedzi'] = bug_replies

                raw_status = str(bug.get('status') or 'nowy').strip().lower()
                if raw_status in ('odpowiedziano', 'odpowiedz', 'replied'):
                    bug['normalized_status'] = 'odpowiedziano'
                elif raw_status in ('zamkniete', 'zamknięte', 'closed', 'rozwiazane', 'rozwiązane'):
                    bug['normalized_status'] = 'zamkniete'
                else:
                    bug['normalized_status'] = 'nowe'
        except Exception as error:
            current_app.logger.error('Błąd pobierania zgłoszeń: %s', error)
            bugs = []
        finally:
            conn.close()

        return render_template('ustawienia_bugs.html', bugs=bugs, current_sort=sort_by, current_filter=filter_by)

    @admin_bp.route('/admin/ustawienia/bugs/respond/<int:bug_id>', methods=['POST'])
    @login_required
    @dynamic_role_required('ustawienia')
    def admin_respond_bug(bug_id):
        """Add another admin reply to a bug report and notify the reporting user."""
        current_filter = request.form.get('current_filter') or request.args.get('filter') or 'all'
        current_sort = request.form.get('current_sort') or request.args.get('sort') or 'id_desc'
        odpowiedz = (request.form.get('odpowiedz_admina') or '').strip()
        if not odpowiedz:
            flash('Treść odpowiedzi nie może być pusta.', 'error')
            return redirect(url_for('admin.admin_ustawienia_bugs', filter=current_filter, sort=current_sort))

        admin_login = session.get('login') or 'admin'

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            _ensure_replies_table(cursor)
            cursor.execute('SELECT id, login FROM zgloszenia_bledow WHERE id = %s', (bug_id,))
            bug = cursor.fetchone()
            if not bug:
                flash('Zgłoszenie nie istnieje.', 'error')
                return redirect(url_for('admin.admin_ustawienia_bugs'))

            # 1. Zapisz kolejną odpowiedź w tabeli wątku odpowiedzi
            cursor.execute(
                """
                INSERT INTO zgloszenia_bledow_odpowiedzi (zgloszenie_id, autor_login, tresc, created_at)
                VALUES (%s, %s, %s, NOW())
                """,
                (bug_id, admin_login, odpowiedz)
            )

            # 2. Zaktualizuj status i ostatnią odpowiedź w głównym zgłoszeniu
            cursor.execute(
                """
                UPDATE zgloszenia_bledow
                SET odpowiedz_admina = %s,
                    odpowiedz_timestamp = NOW(),
                    odpowiedz_by_login = %s,
                    status = 'odpowiedziano'
                WHERE id = %s
                """,
                (odpowiedz, admin_login, bug_id),
            )
            conn.commit()

            try:
                create_notification(
                    typ='bug_reply',
                    tytul='Nowa odpowiedź na Twoje zgłoszenie',
                    tresc=f'Zgłoszenie #{bug_id}: {odpowiedz[:380]}',
                    recipient_login=bug.get('login'),
                    link_url='/moje_zgloszenia_bledow',
                    created_by_user_id=session.get('user_id'),
                )
            except Exception:
                current_app.logger.exception('Nie udało się utworzyć powiadomienia o odpowiedzi na zgłoszenie #%s', bug_id)

            flash('Odpowiedź została dodana do wątku i wysłano powiadomienie.', 'success')
        except Exception as error:
            conn.rollback()
            current_app.logger.exception('Błąd odpowiadania na zgłoszenie #%s: %s', bug_id, error)
            flash('Nie udało się zapisać odpowiedzi.', 'error')
        finally:
            conn.close()

        return redirect(url_for('admin.admin_ustawienia_bugs', filter=current_filter, sort=current_sort))

    @admin_bp.route('/admin/ustawienia/bugs/delete-reply/<int:reply_id>', methods=['POST'])
    @masteradmin_required
    def admin_delete_bug_reply(reply_id):
        """Delete a single reply from thread."""
        current_filter = request.form.get('current_filter') or request.args.get('filter') or 'all'
        current_sort = request.form.get('current_sort') or request.args.get('sort') or 'id_desc'
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            _ensure_replies_table(cursor)
            cursor.execute('DELETE FROM zgloszenia_bledow_odpowiedzi WHERE id = %s', (reply_id,))
            conn.commit()
            flash('Odpowiedź została usunięta z wątku.', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Błąd usuwania odpowiedzi: {e}', 'error')
        finally:
            conn.close()
        return redirect(url_for('admin.admin_ustawienia_bugs', filter=current_filter, sort=current_sort))

    @admin_bp.route('/admin/ustawienia/bugs/delete/<int:bug_id>', methods=['POST'])
    @masteradmin_required
    def admin_delete_bug(bug_id):
        """Delete a bug report and its associated attachments."""
        current_filter = request.form.get('current_filter') or request.args.get('filter') or 'all'
        current_sort = request.form.get('current_sort') or request.args.get('sort') or 'id_desc'
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            _ensure_replies_table(cursor)
            cursor.execute('SELECT zalaczniki FROM zgloszenia_bledow WHERE id = %s', (bug_id,))
            row = cursor.fetchone()
            if row:
                attachments = row['zalaczniki']
                if isinstance(attachments, str):
                    try:
                        attachments = json.loads(attachments)
                    except Exception:
                        attachments = []

                if isinstance(attachments, list):
                    bugs_dir = os.path.join(current_app.static_folder, 'uploads', 'bugs')
                    for attachment in attachments:
                        attachment_path = os.path.join(bugs_dir, attachment)
                        if os.path.exists(attachment_path):
                            try:
                                os.remove(attachment_path)
                            except Exception:
                                pass

                cursor.execute('DELETE FROM zgloszenia_bledow_odpowiedzi WHERE zgloszenie_id = %s', (bug_id,))
                cursor.execute('DELETE FROM zgloszenia_bledow WHERE id = %s', (bug_id,))
                conn.commit()
                flash('Zgłoszenie wraz z wątkiem zostało usunięte.', 'success')
            else:
                flash('Zgłoszenie nie istnieje.', 'error')
        except Exception as error:
            conn.rollback()
            flash(f'Błąd podczas usuwania: {error}', 'error')
        finally:
            conn.close()

        return redirect(url_for('admin.admin_ustawienia_bugs', filter=current_filter, sort=current_sort))