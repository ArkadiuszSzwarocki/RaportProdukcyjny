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
    # Filtrujemy tylko te, które mają dostawcę zewnętrznego (dostawy zewnętrzne)
    receptions = [d for d in dostawy if bool(str(d.get('supplier') or '').strip())]
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
                return redirect(url_for('magazyn_dostawy.reception_view', linia=linia))
            if dostawa and dostawa.get('items'):
                dostawa['items'] = json.loads(dostawa['items'])

        table_sur = get_table_name('magazyn_surowce', linia)
        wszystkie_produkty = set()
        for query, p in [
            ("SELECT DISTINCT nazwa FROM slownik_surowcow WHERE nazwa IS NOT NULL AND TRIM(nazwa) != ''", ()),
            ("SELECT DISTINCT nazwa FROM magazyn_dodatki WHERE linia = %s AND nazwa IS NOT NULL AND TRIM(nazwa) != ''", (linia,))
        ]:
            try:
                cursor.execute(query, p)
                wszystkie_produkty.update([r['nazwa'].strip() for r in cursor.fetchall() if r and r.get('nazwa')])
            except Exception:
                pass
        wszystkie_produkty = sorted(list(wszystkie_produkty))

        try:
            cursor.execute("SELECT id, nazwa, ip, lokalizacja FROM drukarki WHERE aktywna = 1")
            printers = cursor.fetchall()
        except Exception as pe:
            print(f"Error fetching printers in reception_edit: {pe}")

    finally:
        conn.close()

    workflow_steps = [
        {'label': 'Awizacja', 'icon': 'fact_check', 'status': 'AWIZOWANE'},
        {'label': 'Etykiety SSCC', 'icon': 'qr_code_2', 'status': 'W_STREFIE_PRZYJEC'},
        {'label': 'Zadanie Putaway', 'icon': 'forklift', 'status': 'PUTAWAY_IN_PROGRESS'},
        {'label': 'Skan Lokalizacji', 'icon': 'where_to_vote', 'status': 'COMPLETED'},
    ]

    workflow_meta = None
    can_awizuj = False
    can_etykiety = False
    can_assign_putaway = False
    if dostawa:
        from app.services.magazyn_dostawy.commands.delivery_reception_workflow import (
            DeliveryReceptionWorkflow, DeliveryStatus
        )
        current_status = str(dostawa.get('status') or 'SZKIC').upper()
        workflow_meta = DeliveryReceptionWorkflow.get_status_meta(current_status)
        can_awizuj = DeliveryReceptionWorkflow.can_transition(current_status, DeliveryStatus.AWIZOWANE)
        can_etykiety = DeliveryReceptionWorkflow.can_transition(current_status, DeliveryStatus.W_STREFIE_PRZYJEC)
        can_assign_putaway = DeliveryReceptionWorkflow.can_transition(current_status, DeliveryStatus.PUTAWAY_IN_PROGRESS)

    return render_template(
        'magazyn_dostawy/reception_form.html',
        dostawa=dostawa, linia=linia,
        wszystkie_produkty=wszystkie_produkty,
        lokalizacje=['BFOS'] + [f'A{str(i+1).zfill(2)}' for i in range(99)] if linia == 'OSIP' else BUFORY,
        printers=printers,
        now_str=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        workflow_steps=workflow_steps,
        workflow_meta=workflow_meta,
        can_awizuj=can_awizuj,
        can_etykiety=can_etykiety,
        can_assign_putaway=can_assign_putaway,
    )


@magazyn_dostawy_bp.route('/przyjecie/<dostawa_id>/awizuj', methods=['POST'])
def reception_awizuj(dostawa_id):
    """Step 1 web route: proxy to workflow API for awization confirmation."""
    from .api_actions import api_workflow_awizuj
    return api_workflow_awizuj(dostawa_id)


@magazyn_dostawy_bp.route('/przyjecie/<dostawa_id>/etykiety', methods=['POST'])
def reception_etykiety(dostawa_id):
    """Step 2 web route: proxy to workflow API for SSCC generation and printing."""
    from .api_actions import api_workflow_etykiety
    return api_workflow_etykiety(dostawa_id)


@magazyn_dostawy_bp.route('/przyjecie/<dostawa_id>/putaway')
def reception_putaway(dostawa_id):
    """Step 3/4 web view for forklift operator putaway confirmation."""
    linia = request.args.get('linia', 'PSD').upper()
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
        dostawa = cursor.fetchone()
        if not dostawa:
            return redirect(url_for('magazyn_dostawy.reception_view', linia=linia))

        items = json.loads(dostawa.get('items') or '[]')
        active_items = [it for it in items if not it.get('rejected') and not it.get('putaway_confirmed_at')]
        completed_items = [it for it in items if it.get('putaway_confirmed_at')]

        return render_template(
            'magazyn_dostawy/putaway_task.html',
            dostawa=dostawa,
            linia=linia,
            items=active_items,
            completed_count=len(completed_items),
            total_count=len([it for it in items if not it.get('rejected')]),
        )
    finally:
        conn.close()

