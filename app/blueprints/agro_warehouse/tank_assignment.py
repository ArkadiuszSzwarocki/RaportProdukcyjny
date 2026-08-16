"""
Moduł do przypisywania palet do zbiorników produkcyjnych (BB/MZ/KO).

Przepływ:
1. Użytkownik klika w kafelek zbiornika LUB skanuje paletę
2. System sprawdza stan zbiornika
3. Jeśli zajęty → pyta czy opróżnić
4. Przypisuje nową paletę
"""

from flask import request, jsonify, render_template, session
from .blueprint import agro_warehouse_bp
from app.decorators import login_required, dynamic_role_required
from app.db import get_db_connection
from app.services.agro.agro_surowce_service import AgroSurowceService
from app.services.agro.agro_tanks_service import AgroTanksService
import re


def _normalize_tank_code(code):
    """Normalizuje kod zbiornika do BB01, MZ07, KO12 itp."""
    if not code:
        return None
    code = str(code).upper().strip()
    # BB01, BB1, BB 01, BB-01 → BB01
    m = re.match(r'([A-Z]+)[\s-]?0*(\d+)', code)
    if m:
        prefix = m.group(1)
        num = int(m.group(2))
        return f"{prefix}{num:02d}"
    return code


def _is_valid_tank_code(code):
    """Sprawdza czy kod to poprawny zbiornik BB/MZ/KO."""
    if not code:
        return False
    code = _normalize_tank_code(code)
    patterns = [r'^BB\d{2}$', r'^MZ\d{2}$', r'^KO\d{2}$']
    return any(re.match(p, code) for p in patterns)


def _normalize_pallet_scan(scan_value):
    """Normalizuje skan palety do formatu AAA+18 cyfr (np. SUR000...)."""
    if not scan_value:
        return ''
    raw = str(scan_value).strip().upper()
    cleaned = re.sub(r'[^A-Z0-9]', '', raw)
    match = re.search(r'(SUR\d{18})', cleaned)
    if match:
        return match.group(1)
    return cleaned


@agro_warehouse_bp.route('/agro/api/zbiornik/status', methods=['POST'])
@login_required
@dynamic_role_required('agro.magazyn')
def check_tank_status():
    """
    Sprawdza stan zbiornika produkcyjnego.
    
    POST /agro/api/zbiornik/status
    Body: { "zbiornik": "BB15" }
    
    Returns:
        {
            "success": true,
            "zbiornik": "BB15",
            "zajety": true/false,
            "surowce": [
                {
                    "nazwa": "Bm3",
                    "ilosc_kg": 1250.5,
                    "surowiec_id": 123,
                    "ruch_id": 456
                }
            ],
            "suma_kg": 1250.5
        }
    """
    try:
        data = request.get_json() or {}
        zbiornik_raw = data.get('zbiornik', '').strip()
        
        if not zbiornik_raw:
            return jsonify({'success': False, 'message': 'Brak kodu zbiornika'}), 400
        
        zbiornik = _normalize_tank_code(zbiornik_raw)
        
        if not _is_valid_tank_code(zbiornik):
            return jsonify({
                'success': False,
                'message': f'Nieprawidłowy kod zbiornika: {zbiornik_raw}'
            }), 400
        
        # Pobierz stan zbiornika
        linia = 'Agro'
        snapshot = AgroTanksService.get_production_inventory_snapshot(linia=linia, show_empty=False)
        
        # Znajdź wpisy dla tego zbiornika
        surowce_w_zbiorniku = [
            item for item in snapshot
            if _normalize_tank_code(item.get('zbiornik', '')) == zbiornik and item.get('stan_systemowy', 0) > 0
        ]
        
        suma_kg = sum(item.get('stan_systemowy', 0) for item in surowce_w_zbiorniku)
        
        return jsonify({
            'success': True,
            'zbiornik': zbiornik,
            'zajety': len(surowce_w_zbiorniku) > 0,
            'surowce': [
                {
                    'nazwa': item.get('surowiec_nazwa') or item.get('nazwa', ''),
                    'ilosc_kg': item.get('stan_systemowy', 0),
                    'surowiec_id': item.get('surowiec_id'),
                    'ruch_id': item.get('ruch_id'),
                    'lokalizacja': item.get('lokalizacja', '')
                }
                for item in surowce_w_zbiorniku
            ],
            'suma_kg': round(suma_kg, 2)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500


@agro_warehouse_bp.route('/agro/api/zbiornik/oproznij', methods=['POST'])
@login_required
@dynamic_role_required('agro.magazyn')
def empty_tank():
    """
    Opróżnia zbiornik (archiwizacja w produkcji, bez zwrotu do magazynu).
    
    POST /agro/api/zbiornik/oproznij
    Body: { "zbiornik": "BB15", "komentarz": "Zmiana receptury" }
    
    Returns:
        { "success": true, "message": "Zbiornik BB15 opróżniony" }
    """
    try:
        data = request.get_json() or {}
        zbiornik_raw = data.get('zbiornik', '').strip()
        komentarz = data.get('komentarz', '').strip() or 'Opróżniono przez interfejs'
        
        if not zbiornik_raw:
            return jsonify({'success': False, 'message': 'Brak kodu zbiornika'}), 400
        
        zbiornik = _normalize_tank_code(zbiornik_raw)
        
        if not _is_valid_tank_code(zbiornik):
            return jsonify({
                'success': False,
                'message': f'Nieprawidłowy kod zbiornika: {zbiornik_raw}'
            }), 400
        
        worker_login = session.get('login', 'system')
        linia = 'Agro'
        
        # Pobierz stan zbiornika
        snapshot = AgroTanksService.get_production_inventory_snapshot(linia=linia, show_empty=False)
        surowce_w_zbiorniku = [
            item for item in snapshot
            if _normalize_tank_code(item.get('zbiornik', '')) == zbiornik and item.get('stan_systemowy', 0) > 0
        ]
        
        if not surowce_w_zbiorniku:
            return jsonify({
                'success': False,
                'message': f'Zbiornik {zbiornik} jest już pusty'
            }), 400
        
        # Wyzeruj stan w produkcji (archiwizacja bez zwrotu do magazynu)
        from app.db import get_table_name
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            table_ruch = get_table_name('magazyn_ruch', linia)
            table_surowce = get_table_name('magazyn_surowce', linia)
            
            for item in surowce_w_zbiorniku:
                ilosc_zwrotu = item.get('stan_systemowy', 0)
                surowiec_id = item.get('surowiec_id')
                ruch_id = item.get('ruch_id')
                
                if not surowiec_id or not ruch_id:
                    continue
                
                plan_id_val = item.get('plan_id')
                plan_id_val = int(plan_id_val) if plan_id_val not in (None, '', 0, '0') else None
                surowiec_nazwa = item.get('surowiec_nazwa') or item.get('nazwa') or None
                komentarz_db = f"Opróżniono zbiornik {zbiornik} (archiwizacja). {komentarz}"

                # Zarejestruj korektę produkcji do zera (bez zwrotu do magazynu)
                cursor.execute(
                    f"""INSERT INTO {table_ruch}
                        (surowiec_id, surowiec_nazwa, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, potwierdzil_login, potwierdzil_data, plan_id, komentarz, ruch_zrodlowy_id, zbiornik)
                        VALUES (%s, %s, 'INWENTARYZACJA_PROD', %s, %s, 'POTWIERDZONE', %s, NOW(), %s, NOW(), %s, %s, %s, %s)
                    """,
                    (surowiec_id, surowiec_nazwa, -ilosc_zwrotu, 0, worker_login, worker_login, plan_id_val, komentarz_db, ruch_id, zbiornik)
                )

                archived = False
                cursor.execute(
                    f"SELECT id, nr_palety, nazwa, nr_partii, lokalizacja, stan_magazynowy FROM {table_surowce} WHERE id = %s",
                    (surowiec_id,)
                )
                s_row = cursor.fetchone()
                if s_row and float(s_row.get('stan_magazynowy') or 0) <= 0:
                    cursor.execute(
                        """
                        INSERT INTO magazyn_archiwum
                            (original_id, nr_palety, nazwa, typ_palety, linia, nr_partii, waga_ostatnia, lokalizacja_ostatnia, user_login, komentarz)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            s_row.get('id'),
                            s_row.get('nr_palety'),
                            s_row.get('nazwa') or surowiec_nazwa,
                            'surowiec',
                            linia,
                            s_row.get('nr_partii'),
                            s_row.get('stan_magazynowy') or 0,
                            s_row.get('lokalizacja'),
                            worker_login,
                            f"Archiwizacja po oproznieniu zbiornika {zbiornik}",
                        )
                    )
                    cursor.execute(f"DELETE FROM {table_surowce} WHERE id = %s", (surowiec_id,))
                    archived = True
                
                # Log do palety_historia
                history_action = 'ARCHIWIZACJA_Z_PROD' if archived else 'OPROZNIENIE_Z_PROD'
                history_label = 'Archiwizacja' if archived else 'Oproznienie'
                cursor.execute(
                    """INSERT INTO palety_historia
                        (paleta_id, linia, typ_palety, akcja, lokalizacja_zrodlowa, komentarz, user_login, data_ruchu)
                        VALUES (%s, %s, 'surowiec', %s, %s, %s, %s, NOW())
                    """,
                    (
                        surowiec_id,
                        linia,
                        history_action,
                        zbiornik,
                        f"{history_label} z {zbiornik}: {surowiec_nazwa or ''} ({ilosc_zwrotu} kg). {komentarz}",
                        worker_login,
                    )
                )
            
            conn.commit()
            
            return jsonify({
                'success': True,
                'message': f'Zbiornik {zbiornik} opróżniony ({len(surowce_w_zbiorniku)} surowców zarchiwizowano w produkcji)'
            })
            
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500


@agro_warehouse_bp.route('/agro/api/zbiornik/przypisz', methods=['POST'])
@login_required
@dynamic_role_required('agro.magazyn')
def assign_pallet_to_tank():
    """
    Przypisuje paletę surowca do zbiornika produkcyjnego.
    
    POST /agro/api/zbiornik/przypisz
    Body: {
        "zbiornik": "BB15",
        "surowiec_id": 123,  // ID palety z magazyn_surowce
        "ilosc_kg": 1250,    // Opcjonalnie - domyślnie cały stan
        "plan_id": 456       // Opcjonalnie
    }
    
    Returns:
        { "success": true, "message": "Przypisano 1250 kg do zbiornika BB15" }
    """
    try:
        data = request.get_json() or {}
        zbiornik_raw = data.get('zbiornik', '').strip()
        surowiec_id = data.get('surowiec_id')
        ilosc_kg = data.get('ilosc_kg')
        plan_id = data.get('plan_id')
        
        if not zbiornik_raw:
            return jsonify({'success': False, 'message': 'Brak kodu zbiornika'}), 400
        
        if not surowiec_id:
            return jsonify({'success': False, 'message': 'Brak ID surowca'}), 400
        
        zbiornik = _normalize_tank_code(zbiornik_raw)
        
        if not _is_valid_tank_code(zbiornik):
            return jsonify({
                'success': False,
                'message': f'Nieprawidłowy kod zbiornika: {zbiornik_raw}'
            }), 400
        
        worker_login = session.get('login', 'system')
        linia = 'Agro'
        
        # Sprawdź stan palety
        from app.db import get_table_name
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            table_surowce = get_table_name('magazyn_surowce', linia)
            
            cursor.execute(
                f"SELECT id, nazwa, stan_magazynowy, lokalizacja, nr_palety FROM {table_surowce} WHERE id = %s",
                (surowiec_id,)
            )
            paleta = cursor.fetchone()
            
            if not paleta:
                return jsonify({'success': False, 'message': 'Nie znaleziono palety'}), 404
            
            stan_dostepny = float(paleta['stan_magazynowy'] or 0)
            
            if stan_dostepny <= 0:
                return jsonify({
                    'success': False,
                    'message': f'Paleta {paleta["nazwa"]} ma 0 kg w magazynie'
                }), 400
            
            # Jeśli nie podano ilości, użyj całego stanu
            if ilosc_kg is None:
                ilosc_kg = stan_dostepny
            else:
                ilosc_kg = float(ilosc_kg)
            
            if ilosc_kg > stan_dostepny:
                return jsonify({
                    'success': False,
                    'message': f'Za mało surowca (dostępne: {stan_dostepny} kg)'
                }), 400
            
            # Użyj istniejącej metody use_for_production
            success = AgroSurowceService.use_for_production(
                surowiec_id=surowiec_id,
                ilosc=ilosc_kg,
                worker_login=worker_login,
                plan_id=plan_id,
                linia=linia,
                komentarz=f'Przypisano do zbiornika {zbiornik}',
                zbiornik=zbiornik
            )
            
            if success:
                if zbiornik.startswith('CZ') and plan_id:
                    try:
                        table_plan = get_table_name('plan_produkcji', linia)
                        nr_palety_sscc = paleta.get('nr_palety')
                        if nr_palety_sscc:
                            cursor.execute(f"UPDATE {table_plan} SET skan_sscc = %s WHERE id = %s", (nr_palety_sscc, plan_id))
                            conn.commit()
                    except Exception as e:
                        print(f"Error saving skan_sscc for CZ: {e}")

                return jsonify({
                    'success': True,
                    'message': f'Przypisano {ilosc_kg} kg ({paleta["nazwa"]}) do zbiornika {zbiornik}'
                })
            else:
                return jsonify({'success': False, 'message': 'Błąd podczas przypisywania'}), 500
                
        except Exception as e:
            raise e
        finally:
            conn.close()
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500


@agro_warehouse_bp.route('/agro/api/zbiornik/znajdz-palete', methods=['POST'])
@login_required
@dynamic_role_required('agro.magazyn')
def find_pallet_by_scan():
    """
    Wyszukuje paletę po zeskanowanym kodzie (nr_palety).
    
    POST /agro/api/zbiornik/znajdz-palete
    Body: { "scan": "SUR000123" }
    
    Returns:
        {
            "success": true,
            "paleta": {
                "id": 123,
                "nr_palety": "SUR000123",
                "nazwa": "Bm3",
                "stan_kg": 1250,
                "lokalizacja": "R021002"
            }
        }
    """
    try:
        data = request.get_json() or {}
        scan_raw = data.get('scan', '').strip()
        scan = _normalize_pallet_scan(scan_raw)
        
        if not scan:
            return jsonify({'success': False, 'message': 'Brak kodu do wyszukania'}), 400
        
        linia = 'Agro'
        from app.db import get_table_name
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            table_surowce = get_table_name('magazyn_surowce', linia)
            
            cursor.execute(
                f"""SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja 
                    FROM {table_surowce} 
                    WHERE REPLACE(REPLACE(UPPER(nr_palety), '-', ''), ' ', '') = %s
                       OR id = %s
                    LIMIT 1
                """,
                (scan, scan if scan.isdigit() else 0)
            )
            paleta = cursor.fetchone()

            if not paleta and re.match(r'^\d{18}$', scan):
                scan_with_prefix = f"SUR{scan}"
                cursor.execute(
                    f"""SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja 
                        FROM {table_surowce} 
                        WHERE REPLACE(REPLACE(UPPER(nr_palety), '-', ''), ' ', '') = %s
                        LIMIT 1
                    """,
                    (scan_with_prefix,)
                )
                paleta = cursor.fetchone()
            
            if not paleta:
                return jsonify({
                    'success': False,
                    'message': f'Nie znaleziono palety: {scan_raw or scan}'
                }), 404
            
            return jsonify({
                'success': True,
                'paleta': {
                    'id': paleta['id'],
                    'nr_palety': paleta.get('nr_palety', ''),
                    'nazwa': paleta['nazwa'],
                    'stan_kg': float(paleta['stan_magazynowy'] or 0),
                    'lokalizacja': paleta.get('lokalizacja', '')
                }
            })
            
        finally:
            conn.close()
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500
