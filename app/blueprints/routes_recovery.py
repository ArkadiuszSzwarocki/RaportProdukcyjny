"""Job recovery and resumption routes (formerly routes_api.py WZNOWIENIE sections)."""

from flask import Blueprint, request, jsonify
from datetime import date, timedelta
from app.db import get_db_connection
from app.decorators import login_required

recovery_bp = Blueprint('recovery', __name__)


@recovery_bp.route('/wznow_zlecenia_z_wczoraj', methods=['POST'])
@login_required
def wznow_zlecenia_z_wczoraj():
    """
    Endpoint wznawia wszystkie zlecenia ze statusem 'wstrzymane' 
    z poprzedniego dnia (zmieniam status na 'w toku').
    """
    try:
        print(f"[WZNOW-WCZORAJ] Starting auto-resume handler")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Poprzedni dzień
        wczoraj = date.today() - timedelta(days=1)
        wczoraj_str = wczoraj.strftime('%Y-%m-%d')
        
        print(f"[WZNOW-WCZORAJ] Querying for plans from {wczoraj_str}")
        
        # Wznów wszystkie zlecenia w statusie 'wstrzymane' z poprzedniego dnia
        resume_query = """
            UPDATE plan_produkcji 
            SET status = 'w toku' 
            WHERE DATE(data_planu) = %s 
            AND status = 'wstrzymane'
        """
        
        cursor.execute(resume_query, (wczoraj_str,))
        resumed_count = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"[WZNOW-WCZORAJ] OK Success: Resumed {resumed_count} plans from {wczoraj_str}")
        
        return jsonify({
            "success": True,
            "resumed_count": resumed_count,
            "message": f"Wznowiono {resumed_count} zleceń z poprzedniego dnia ({wczoraj_str})",
            "date_resumed": wczoraj_str
        }), 200
        
    except Exception as e:
        print(f"[WZNOW-WCZORAJ] ERROR Error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "Błąd przy wznowienia zleceń z poprzedniego dnia"
        }), 500


@recovery_bp.route('/wznow_zlecenia_sekcji/<sekcja>', methods=['POST'])
@login_required
def wznow_zlecenia_sekcji(sekcja):
    """
    Endpoint ręcznego wznowienia wszystkich zleceń 'wstrzymane' 
    z poprzedniego dnia dla wybranej sekcji.
    """
    try:
        print(f"[WZNOW-SEKCJA] Starting handler for sekcja={sekcja}")
        
        # Walidacja sekcji
        if sekcja not in ['Zasyp', 'Workowanie', 'Pakowanie', 'Magazyn']:
            print(f"[WZNOW-SEKCJA] ✗ Invalid sekcja: {sekcja}")
            return jsonify({
                "success": False,
                "error": f"Nieznana sekcja: {sekcja}",
                "message": "Sekcja musi być jedną z: Zasyp, Workowanie, Pakowanie, Magazyn"
            }), 400
        
        print(f"[WZNOW-SEKCJA] Sekcja valid: {sekcja}")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Poprzedni dzień
        wczoraj = date.today() - timedelta(days=1)
        wczoraj_str = wczoraj.strftime('%Y-%m-%d')
        
        print(f"[WZNOW-SEKCJA] Querying plans from {wczoraj_str} for sekcja={sekcja}")
        
        # Wznów wszystkie zlecenia 'wstrzymane' z poprzedniego dnia dla tej sekcji
        resume_query = """
            UPDATE plan_produkcji 
            SET status = 'w toku' 
            WHERE DATE(data_planu) = %s 
            AND sekcja = %s 
            AND status = 'wstrzymane'
        """
        
        cursor.execute(resume_query, (wczoraj_str, sekcja))
        resumed_count = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"[WZNOW-SEKCJA] ✓ Success: Resumed {resumed_count} plans for sekcja={sekcja} from {wczoraj_str}")
        
        return jsonify({
            "success": True,
            "resumed_count": resumed_count,
            "sekcja": sekcja,
            "message": f"✅ Wznowiono {resumed_count} zleceń dla {sekcja} z poprzedniego dnia ({wczoraj_str})",
            "date_resumed": wczoraj_str
        }), 200
        
    except Exception as e:
        print(f"[WZNOW-SEKCJA] ✗ Error for sekcja={sekcja}: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            "success": False,
            "error": str(e),
            "message": f"Błąd przy wznowienia zleceń dla {sekcja}"
        }), 500

