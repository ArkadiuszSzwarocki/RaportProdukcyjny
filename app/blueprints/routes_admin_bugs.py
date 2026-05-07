import json
import os

from flask import current_app, flash, redirect, render_template, request, session, url_for

from app.db import get_db_connection
from app.decorators import dynamic_role_required, login_required


def register_admin_bug_routes(admin_bp, *, create_notification):
    @admin_bp.route('/admin/ustawienia/bugs')
    @login_required
    @dynamic_role_required('ustawienia')
    def admin_ustawienia_bugs():
        """View manually reported bugs from database."""
        sort_by = request.args.get('sort', 'id_desc')
        
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
            cursor.execute(f'SELECT * FROM zgloszenia_bledow ORDER BY {order_clause}')
            bugs = cursor.fetchall()

            for bug in bugs:
                if isinstance(bug.get('zalaczniki'), str):
                    bug['zalaczniki'] = json.loads(bug['zalaczniki'])
                elif not bug.get('zalaczniki'):
                    bug['zalaczniki'] = []
        except Exception as error:
            current_app.logger.error('Błąd pobierania zgłoszeń: %s', error)
            bugs = []
        finally:
            conn.close()

        return render_template('ustawienia_bugs.html', bugs=bugs, current_sort=sort_by)

    @admin_bp.route('/admin/ustawienia/bugs/respond/<int:bug_id>', methods=['POST'])
    @login_required
    @dynamic_role_required('ustawienia')
    def admin_respond_bug(bug_id):
        """Add admin reply to a bug report and notify the reporting user."""
        odpowiedz = (request.form.get('odpowiedz_admina') or '').strip()
        if not odpowiedz:
            flash('Treść odpowiedzi nie może być pusta.', 'error')
            return redirect(url_for('admin.admin_ustawienia_bugs'))

        admin_login = session.get('login') or 'admin'

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute('SELECT id, login FROM zgloszenia_bledow WHERE id = %s', (bug_id,))
            bug = cursor.fetchone()
            if not bug:
                flash('Zgłoszenie nie istnieje.', 'error')
                return redirect(url_for('admin.admin_ustawienia_bugs'))

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
                    tytul='Odpowiedź na Twoje zgłoszenie błędu',
                    tresc=f'Zgłoszenie #{bug_id}: {odpowiedz[:380]}',
                    recipient_login=bug.get('login'),
                    link_url='/moje_zgloszenia_bledow',
                    created_by_user_id=session.get('user_id'),
                )
            except Exception:
                current_app.logger.exception('Nie udało się utworzyć powiadomienia o odpowiedzi na zgłoszenie #%s', bug_id)

            flash('Odpowiedź została zapisana i wysłano powiadomienie.', 'success')
        except Exception as error:
            conn.rollback()
            current_app.logger.exception('Błąd odpowiadania na zgłoszenie #%s: %s', bug_id, error)
            flash('Nie udało się zapisać odpowiedzi.', 'error')
        finally:
            conn.close()

        return redirect(url_for('admin.admin_ustawienia_bugs'))

    @admin_bp.route('/admin/ustawienia/bugs/delete/<int:bug_id>', methods=['POST'])
    @login_required
    @dynamic_role_required('ustawienia')
    def admin_delete_bug(bug_id):
        """Delete a bug report and its associated attachments."""
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute('SELECT zalaczniki FROM zgloszenia_bledow WHERE id = %s', (bug_id,))
            row = cursor.fetchone()
            if row:
                attachments = row['zalaczniki']
                if isinstance(attachments, str):
                    attachments = json.loads(attachments)

                bugs_dir = os.path.join(current_app.static_folder, 'uploads', 'bugs')
                for attachment in attachments:
                    attachment_path = os.path.join(bugs_dir, attachment)
                    if os.path.exists(attachment_path):
                        os.remove(attachment_path)

                cursor.execute('DELETE FROM zgloszenia_bledow WHERE id = %s', (bug_id,))
                conn.commit()
                flash('Zgłoszenie zostało usunięte.', 'success')
            else:
                flash('Zgłoszenie nie istnieje.', 'error')
        except Exception as error:
            conn.rollback()
            flash(f'Błąd podczas usuwania: {error}', 'error')
        finally:
            conn.close()

        return redirect(url_for('admin.admin_ustawienia_bugs'))