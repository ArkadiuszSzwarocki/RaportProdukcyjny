from flask import render_template, request, jsonify, redirect, url_for, current_app, session
import traceback
from app.db import get_db_connection, get_table_name
from app.decorators import login_required
from app.services.magazyn_dostawy.delivery_queries import DeliveryQueries
from app.services.magazyn_dostawy.delivery_command_service import DeliveryCommandService
from app.services.magazyn_dostawy.acceptance_service import AcceptanceService
from app.services.magazyn_dostawy.location_service import LocationService
from app.utils.pallet_label import prepare_pallet_label_data
from app.utils.pallet_id import generate_pallet_id
from ..config import (
    LOKALIZACJE_SZCZEGOLOWE, BUFORY, LOKALIZACJE, LOKALIZACJE_CEL,
    _safe_float, _safe_datetime_str, _format_label_weight
)
import json
from datetime import datetime
from ..base import magazyn_dostawy_bp

@magazyn_dostawy_bp.route('/przyjecie')
def reception_view():
    """Widok listy przyjęć zewnętrznych."""
    linia = request.args.get('linia', 'PSD').upper()
    dostawy = DeliveryQueries.get_dostawy(linia)
    # Filtrujemy tylko te, które nie mają lokalizacji źródłowej (zewnętrzne)
    receptions = [d for d in dostawy if not d.get('lokalizacja_z')]
    return render_template('magazyn_dostawy/lista_receptions.html', dostawy=receptions, linia=linia)

@magazyn_dostawy_bp.route('/przyjecie/nowe')
@magazyn_dostawy_bp.route('/przyjecie/<dostawa_id>')
def reception_edit(dostawa_id=None):
    """Formularz przyjęcia zewnętrznego do buforów."""
    linia = request.args.get('linia', 'PSD').upper()
    conn = get_db_connection()
    dostawa = None
    wszystkie_produkty = []
    printers = []
    try:
        cursor = conn.cursor(dictionary=True)
        if dostawa_id:
            cursor.execute("SELECT * FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
            dostawa = cursor.fetchone()
            if dostawa and str(dostawa.get('status') or '').upper() == 'COMPLETED':
                return redirect(url_for('magazyn_dostawy.raport_przesuniecia', dostawa_id=dostawa_id, linia=linia))
            if dostawa and dostawa.get('items'):
                dostawa['items'] = json.loads(dostawa['items'])

        table_sur = get_table_name('magazyn_surowce', linia)
        table_opk = get_table_name('magazyn_opakowania', linia)
        wszystkie_produkty = set()
        for query, p in [
            ("SELECT DISTINCT nazwa FROM slownik_surowcow", ()),
            (f"SELECT DISTINCT nazwa FROM {table_sur}", ()),
            (f"SELECT DISTINCT nazwa FROM {table_opk}", ()),
            ("SELECT DISTINCT nazwa FROM magazyn_dodatki WHERE linia = %s", (linia,))
        ]:
            cursor.execute(query, p)
            wszystkie_produkty.update([r['nazwa'] for r in cursor.fetchall() if r and r.get('nazwa')])
        wszystkie_produkty = sorted(list(wszystkie_produkty))

        try:
            cursor.execute("SELECT id, nazwa, ip, lokalizacja FROM drukarki WHERE aktywna = 1")
            printers = cursor.fetchall()
        except Exception as pe:
            print(f"Error fetching printers in reception_edit: {pe}")

    finally:
        conn.close()

    return render_template(
        'magazyn_dostawy/reception_form.html',
        dostawa=dostawa, linia=linia,
        wszystkie_produkty=wszystkie_produkty,
        lokalizacje=BUFORY,
        printers=printers,
        now_str=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )

