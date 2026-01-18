# app.py
from flask import Flask, render_template, request, redirect, session, url_for, send_file, flash
from waitress import serve
from datetime import date, datetime, timedelta
import urllib.parse
import os

# Importy modułów
from config import SECRET_KEY
from db import get_db_connection, setup_database
from raporty import generuj_excel, generuj_pdf, format_godziny

# Importy Blueprintów (DODANO routes_zarzad)
from routes_admin import admin_bp
from routes_api import api_bp
from routes_zarzad import zarzad_bp  # <--- NOWE

from decorators import login_required
# app.py (fragment)
from routes_planista import planista_bp  # <--- DODAJ IMPORT

# ...
app.register_blueprint(admin_bp)
app.register_blueprint(api_bp)
app.register_blueprint(planista_bp) # <--- ZAREJESTRUJ
# ...

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.jinja_env.add_extension('jinja2.ext.do')

# Rejestracja Blueprintów
app.register_blueprint(admin_bp)
app.register_blueprint(api_bp)
app.register_blueprint(zarzad_bp) # <--- REJESTRACJA

app.jinja_env.filters['format_czasu'] = format_godziny
setup_database()

# --- GŁÓWNE ROUTY (Login, Logout, Index, Zamknij zmianę) ---
# Te routy zostają w app.py, ponieważ są kluczowe dla działania aplikacji
# lub można je przenieść do routes_main.py w kolejnym kroku.

# W pliku app.py znajdź funkcję login i podmień ją na tę wersję:

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login = request.form['login']
        haslo = request.form['haslo']
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT rola FROM uzytkownicy WHERE login = %s AND haslo = %s", (login, haslo))
        user = cursor.fetchone()
        conn.close()
        
        if user: 
            session['zalogowany'] = True
            session['rola'] = user[0]
            
            # --- NOWA LOGIKA PRZEKIEROWANIA ---
            if session['rola'] == 'planista':
                return redirect(url_for('planista.panel_planisty'))
            # ----------------------------------
            
            return redirect('/')
            
        return render_template('login.html', message="Błędne dane!")
    return render_template('login.html')

@app.route('/')
@login_required
def index():
    # ... (bez zmian) ...
    pass

# Pozostałe endpointy operacyjne (wyslij_raport_email, zamknij_zmiane) 
# mogą zostać tutaj lub zostać przeniesione do routes_api.py


if __name__ == '__main__':
    print("🚀 Serwer wystartował: http://YOUR_IP_ADDRESS:8082")
    serve(app, host='0.0.0.0', port=8082, threads=6)