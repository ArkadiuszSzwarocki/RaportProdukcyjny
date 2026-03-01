"""Overtime routes - handles overtime request endpoints."""

from flask import Blueprint, request, redirect, url_for, flash, session, render_template, current_app, jsonify
from datetime import date, datetime
from app.db import get_db_connection
from app.decorators import login_required, roles_required
from app.services.overtime_service import OvertimeService

overtime_bp = Blueprint('overtime', __name__)

def bezpieczny_powrot():
    """Return to appropriate view based on user role and context."""
    if session.get('rola') == 'planista' or request.form.get('widok_powrotu') == 'planista':
        data = request.form.get('data_planu') or request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
        return url_for('planista.panel_planisty', data=data)
    sekcja = request.args.get('sekcja') or request.form.get('sekcja', 'Zasyp')
    data = request.form.get('data_planu') or request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
    return url_for('main.index', sekcja=sekcja, data=data)


# =============== NADGODZINY ================
@overtime_bp.route('/nadgodziny/submit', methods=['POST'])
@login_required
def submit_nadgodziny():
    """Submit overtime request."""
    pracownik_id = session.get('pracownik_id') or request.form.get('pracownik_id')
    if not pracownik_id:
        flash('Brak przypisanego pracownika do konta.', 'warning')
        return redirect(url_for('panels.moje_godziny'))
    
    data_str = request.form.get('data')
    ilosc_nadgodzin_str = request.form.get('ilosc_nadgodzin')
    powod = request.form.get('powod') or ''
    
    try:
        data = datetime.strptime(data_str, '%Y-%m-%d').date() if data_str else None
        ilosc_nadgodzin = float(ilosc_nadgodzin_str) if ilosc_nadgodzin_str else 0.0
    except Exception:
        flash('Nieprawidłowy format danych.', 'warning')
        return redirect(url_for('panels.moje_godziny'))
    
    success, message, _ = OvertimeService.submit_overtime_request(
        pracownik_id=int(pracownik_id),
        data=data,
        ilosc_nadgodzin=ilosc_nadgodzin,
        powod=powod
    )
    
    flash(message, 'success' if success else 'warning')
    return redirect(url_for('panels.moje_godziny'))


@overtime_bp.route('/nadgodziny/<int:nid>/approve', methods=['POST'])
@roles_required('lider', 'admin')
def approve_nadgodziny(nid):
    """Approve overtime request."""
    try:
        current_app.logger.info(f"[OVERTIME_APPROVE] nid={nid}")
        lider_id = session.get('pracownik_id')
        
        if not lider_id:
            raise ValueError("Brak ID lidera w sesji")
        
        success, message = OvertimeService.approve_overtime_request(nid, lider_id)
        current_app.logger.info(f"[OVERTIME_APPROVE] success={success}, message={message}")
        
        # Return JSON dla AJAX żądań
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': success, 'message': message}), 200 if success else 400
        
        flash(message, 'success' if success else 'warning')
        return redirect(bezpieczny_powrot())
    except Exception as e:
        current_app.logger.exception(f"[OVERTIME_APPROVE] Exception: {str(e)}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500
        raise


@overtime_bp.route('/nadgodziny/<int:nid>/reject', methods=['POST'])
@roles_required('lider', 'admin')
def reject_nadgodziny(nid):
    """Reject overtime request."""
    try:
        current_app.logger.info(f"[OVERTIME_REJECT] nid={nid}")
        lider_id = session.get('pracownik_id')
        
        if not lider_id:
            raise ValueError("Brak ID lidera w sesji")
        
        success, message = OvertimeService.reject_overtime_request(nid, lider_id)
        current_app.logger.info(f"[OVERTIME_REJECT] success={success}, message={message}")
        
        # Return JSON dla AJAX żądań
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': success, 'message': message}), 200 if success else 400
        
        flash(message, 'success' if success else 'warning')
        return redirect(bezpieczny_powrot())
    except Exception as e:
        current_app.logger.exception(f"[OVERTIME_REJECT] Exception: {str(e)}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500
        raise


@overtime_bp.route('/nadgodziny/pending', methods=['GET'])
@roles_required('lider', 'admin')
def get_pending_nadgodziny():
    """Get pending overtime requests for leader approval."""
    requests = OvertimeService.get_pending_requests()
    return jsonify(requests)
