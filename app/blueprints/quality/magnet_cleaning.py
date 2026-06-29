from flask import Blueprint, jsonify, request, session, render_template, current_app
from app.services.magnet_cleaning_service import MagnetCleaningService
from app.decorators import login_required, roles_required

magnet_cleaning_bp = Blueprint('magnet_cleaning', __name__, url_prefix='/quality/magnet-cleaning')

@magnet_cleaning_bp.route('/pending', methods=['GET'])
@login_required
def get_pending():
    """Pobiera listę oczekujących czyszczeń do potwierdzenia. Zwraca JSON."""
    service = MagnetCleaningService()
    try:
        tasks = service.get_pending_tasks()
        return jsonify({
            'success': True,
            'tasks': [
                {
                    'id': t.id,
                    'linia': t.linia,
                    'data_planu': t.data_planu.isoformat(),
                    'status': t.status
                } for t in tasks
            ]
        })
    except Exception as e:
        current_app.logger.error(f"Error fetching pending cleanings: {e}")
        return jsonify({'success': False, 'message': 'Błąd serwera'}), 500

@magnet_cleaning_bp.route('/confirm', methods=['POST'])
@roles_required('operator', 'operator_psd', 'operator_agro', 'lider', 'zarzad', 'admin', 'masteradmin')
def confirm_cleaning():
    """Potwierdza wykonanie czyszczenia."""
    data = request.json or {}
    record_id = data.get('id')
    komentarz = data.get('komentarz')
    
    if not record_id:
        return jsonify({'success': False, 'message': 'Brak ID zadania'}), 400
        
    login = session.get('login', 'Nieznany')
    service = MagnetCleaningService()
    
    try:
        success = service.confirm_cleaning(record_id, login, komentarz)
        if success:
            return jsonify({'success': True, 'message': 'Wyczyszczenie magnesu zostało potwierdzone.'})
        else:
            return jsonify({'success': False, 'message': 'Zadanie już potwierdzone lub nie istnieje.'}), 400
    except Exception as e:
        current_app.logger.error(f"Error confirming cleaning: {e}")
        return jsonify({'success': False, 'message': 'Błąd serwera'}), 500

@magnet_cleaning_bp.route('/history', methods=['GET'])
@roles_required('laborant', 'lider', 'zarzad', 'admin', 'masteradmin')
def get_history():
    """Widok historii czyszczenia (dla laborantów i zarządu)."""
    service = MagnetCleaningService()
    try:
        history = service.get_cleaning_history(limit=200)
        # Renderowanie szablonu HTML dla podglądu
        return render_template('quality/magnet_cleaning_history.html', history=history)
    except Exception as e:
        current_app.logger.error(f"Error viewing magnet history: {e}")
        return "Wystąpił błąd podczas ładowania historii.", 500

@magnet_cleaning_bp.route('/ad-hoc', methods=['POST'])
@roles_required('operator', 'operator_psd', 'operator_agro', 'lider', 'zarzad', 'admin', 'masteradmin')
def adhoc_cleaning():
    """Zgłasza wyczyszczenie magnesu poza harmonogramem."""
    data = request.json or {}
    linia = data.get('linia')
    komentarz = data.get('komentarz', '')
    
    if not linia:
        return jsonify({'success': False, 'message': 'Brak informacji o linii'}), 400
        
    login = session.get('login', 'Nieznany')
    service = MagnetCleaningService()
    
    try:
        service.record_adhoc_cleaning(linia, login, komentarz)
        return jsonify({'success': True, 'message': 'Zarejestrowano czyszczenie poza harmonogramem.'})
    except Exception as e:
        current_app.logger.error(f"Error recording ad-hoc cleaning: {e}")
        return jsonify({'success': False, 'message': 'Błąd serwera'}), 500
