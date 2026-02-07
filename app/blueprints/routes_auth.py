"""Authentication routes (login, logout, issue reporting)."""

from flask import Blueprint, render_template, request, redirect, session, flash, make_response
from datetime import datetime
from werkzeug.security import check_password_hash
import os

from app.decorators import login_required
from app.db import get_db_connection
from app.utils.validation import require_field

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login with session management."""
    if request.method == 'POST':
        # Validate required form fields via central helper
        try:
            login_field = require_field(request.form, 'login')
            password_field = require_field(request.form, 'haslo')
        except Exception as e:
            flash(str(e), 'danger')
            return redirect('/login')

        conn = get_db_connection()
        cursor = conn.cursor()
        # Pobierz opcjonalne pole pracownik_id by mapować konto na rekord pracownika
        cursor.execute("SELECT id, haslo, rola, COALESCE(pracownik_id, NULL) FROM uzytkownicy WHERE login = %s", (login_field,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            uid, hashed, rola, pracownik_id = row[0], row[1], row[2], row[3]
            if hashed and check_password_hash(hashed, password_field):
                session['zalogowany'] = True
                # Normalize role to lowercase to avoid case-sensitivity issues in templates
                session['rola'] = (rola or '').lower()
                # Zapisz login i powiązanie pracownika w sesji (może być None)
                session['login'] = login_field
                session['pracownik_id'] = int(pracownik_id) if pracownik_id is not None else None
                
                # Log login with current process PID
                from flask import current_app
                current_app.logger.info(f"[LOGIN] User '{login_field}' logged in successfully (PID: {os.getpid()})")
                
                # Pobierz imię_nazwisko z tabeli pracownicy dla wyświetlenia w belce górnej
                imie_nazwisko = None
                if pracownik_id:
                    try:
                        conn2 = get_db_connection()
                        cursor2 = conn2.cursor()
                        cursor2.execute("SELECT imie_nazwisko FROM pracownicy WHERE id = %s", (pracownik_id,))
                        p_row = cursor2.fetchone()
                        if p_row:
                            imie_nazwisko = p_row[0]
                        cursor2.close()
                        conn2.close()
                    except Exception:
                        pass
                session['imie_nazwisko'] = imie_nazwisko or login_field
                
                # Use location.replace on client to avoid keeping login page in history
                target = '/planista' if rola == 'planista' else '/'
                html = f"""<!doctype html><html><head><meta charset=\"utf-8\"><title>Logowanie...</title></head><body><script>window.location.replace('{target}');</script></body></html>"""
                try:
                    resp = make_response(html)
                    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
                    resp.headers['Pragma'] = 'no-cache'
                    return resp
                except Exception:
                    return html, 200
        
        flash("Błędne dane!", 'danger')
        return redirect('/login')
    
    # If already logged in, don't show login form — redirect to app
    if session.get('zalogowany'):
        return redirect('/')
    
    try:
        resp = make_response(render_template('login.html'))
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        return resp
    except Exception:
        return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    """Clear session and redirect to login."""
    session.clear()
    return redirect('/login')


@auth_bp.route('/zglos')
@login_required
def report_issue():
    """Report an issue with optional section filter."""
    sekcja = request.args.get('sekcja', 'Zasyp')
    now_time = datetime.now().strftime('%H:%M')
    return render_template('report_issue.html', sekcja=sekcja, now_time=now_time)


