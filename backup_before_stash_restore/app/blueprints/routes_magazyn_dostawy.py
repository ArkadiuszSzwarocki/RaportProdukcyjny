from flask import Blueprint, render_template, request, jsonify, session
from app.db import get_db_connection, get_table_name
from app.services.magazyn_dostawy_service import MagazynDostawyService
import json
from datetime import datetime

magazyn_dostawy_bp = Blueprint('magazyn_dostawy', __name__, url_prefix='/magazyn-dostawy')

# Lokalizacje z systemu Mleczna Droga
LOKALIZACJE_ZRODLO = [
    'MS01', 'MP01', 'MDM01', 'MOP01', 'MGW01', 'MGW02',
    'OSIP', 'BF_MS01', 'BF_MP01', 'KO01', 'PSD',
    'RAMPA', 'MIX01', 'W_TRANZYCIE_OSIP',
]

# Regały R04 (20 poz.), R05 (20 poz.), R06 (10 poz.), R07 (20 poz.)
_r04 = [f'R04{str(i+1).zfill(2)}01' for i in range(20)]
_r05 = [f'R05{str(i+1).zfill(2)}01' for i in range(20)]
_r06 = [f'R06{str(i+1).zfill(2)}01' for i in range(10)]
_r07 = [f'R07{str(i+1).zfill(2)}01' for i in range(20)]
# OSIP – 77 lokalizacji OS01..OS77
_osip = [f'OS{str(i+1).zfill(2)}' for i in range(77)]
# Stanowiska produkcyjne BB01..BB24, MZ01..MZ06
_bb = [f'BB{str(i+1).zfill(2)}' for i in range(24)]
_mz = ['MZ01', 'MZ02', 'MZ03', 'MZ04', 'MZ05', 'MZ06', 'MZ05-01', 'MZ06-01']

LOKALIZACJE_SZCZEGOLOWE = {
    'Magazyny': LOKALIZACJE_ZRODLO,
    'Regał R04': _r04,
    'Regał R05': _r05,
    'Regał R06': _r06,
    'Regał R07': _r07,
    'OSIP (OS01-OS77)': _osip,
    'Stanowiska BB': _bb,
    'Stanowiska MZ': _mz,
}

# Płaska lista na potrzeby selecta źródło/cel
LOKALIZACJE = LOKALIZACJE_ZRODLO + ['R04', 'R05', 'R06', 'R07']

@magazyn_dostawy_bp.route('/')
def lista_dostaw():
    linia = request.args.get('linia', 'PSD').upper()
    dostawy = MagazynDostawyService.get_dostawy(linia)
    return render_template('magazyn_dostawy/lista.html', dostawy=dostawy, linia=linia)

@magazyn_dostawy_bp.route('/oczekujace')
def oczekujace():
    linia = request.args.get('linia', 'PSD').upper()
    dostawy = MagazynDostawyService.get_oczekujace(linia)
    return render_template('magazyn_dostawy/oczekujace.html',
                           dostawy=dostawy, linia=linia,
                           lok_grupy=LOKALIZACJE_SZCZEGOLOWE)

@magazyn_dostawy_bp.route('/raport')
def raport():
    linia = request.args.get('linia', 'PSD').upper()
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    dostawy = MagazynDostawyService.get_raport(date_from, date_to)
    return render_template('magazyn_dostawy/raport.html',
                           dostawy=dostawy, linia=linia,
                           date_from=date_from, date_to=date_to,
                           now_str=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

@magazyn_dostawy_bp.route('/nowa')
@magazyn_dostawy_bp.route('/<dostawa_id>')
def edycja_dostawy(dostawa_id=None):
    linia = request.args.get('linia', 'PSD').upper()
    conn = get_db_connection()
    dostawa = None
    wszystkie_produkty = []
    try:
        cursor = conn.cursor(dictionary=True)
        if dostawa_id:
            cursor.execute("SELECT * FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
            dostawa = cursor.fetchone()
            if dostawa and dostawa.get('items'):
                dostawa['items'] = json.loads(dostawa['items'])

        table_sur = get_table_name('magazyn_surowce', linia)
        table_opk = get_table_name('magazyn_opakowania', linia)
        cursor.execute(f"SELECT DISTINCT nazwa FROM {table_sur} UNION SELECT DISTINCT nazwa FROM {table_opk}")
        wszystkie_produkty = [r['nazwa'] for r in cursor.fetchall()]
    finally:
        conn.close()

    return render_template(
        'magazyn_dostawy/edycja.html',
        dostawa=dostawa, linia=linia,
        wszystkie_produkty=wszystkie_produkty,
        lokalizacje=LOKALIZACJE
    )

@magazyn_dostawy_bp.route('/api/zapisz', methods=['POST'])
def zapisz_dostawe():
    success, result = MagazynDostawyService.save_dostawa(request.json, session.get('login', 'system'))
    if success:
        return jsonify({"success": True, "id": result})
    return jsonify({"success": False, "error": result}), 500

@magazyn_dostawy_bp.route('/api/przyjmij-pozycje/<dostawa_id>', methods=['POST'])
def przyjmij_pozycje(dostawa_id):
    data = request.json
    success, error, result = MagazynDostawyService.accept_item(
        dostawa_id, data.get('item_id'), data.get('lokalizacja', '').strip(), session.get('login', 'system')
    )
    if success:
        return jsonify({
            "success": True,
            "all_accepted": result["all_accepted"],
            "accepted_count": result["accepted_count"],
            "total": result["total"],
            "message": f"Przyjęto pomyślnie."
        })
    return jsonify({"success": False, "error": error}), 400

@magazyn_dostawy_bp.route('/api/sprawdz-lokalizacje', methods=['POST'])
def sprawdz_lokalizacje():
    data = request.json
    occupied, content, items = MagazynDostawyService.check_location(
        data.get('lokalizacja', '').strip(), data.get('linia', 'PSD').upper()
    )
    if occupied:
        return jsonify({
            "success": True,
            "occupied": True,
            "items": items,
            "content": content,
            "message": f"Lokalizacja zajęta przez: {content}"
        })
    return jsonify({"success": True, "occupied": False, "message": "Lokalizacja wolna"})


@magazyn_dostawy_bp.route('/api/suggest-locations', methods=['GET'])
def suggest_locations():
    prefix = request.args.get('prefix', '')
    linia = request.args.get('linia', 'PSD').upper()
    limit = request.args.get('limit', default=40, type=int)
    items = MagazynDostawyService.suggest_locations(prefix=prefix, linia=linia, limit=limit)
    return jsonify({"success": True, "items": items})
