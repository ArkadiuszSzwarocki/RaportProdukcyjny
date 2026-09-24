from flask import Blueprint, request, redirect, flash, session, current_app, jsonify, url_for
from datetime import date
import time

from app.decorators import login_required, roles_required, masteradmin_required
from app.db import get_db_connection, get_table_name

shifts_bp = Blueprint('shifts', __name__)


def _is_ajax_request():
    return (
        request.is_json
        or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json'
    )


@shifts_bp.route('/add_shift_note', methods=['POST'])
@login_required
def add_shift_note():
    """Create a new shift note."""
    if request.is_json:
        data = request.get_json(silent=True) or {}
        note = data.get('note', '').strip()
        pracownik_id = data.get('pracownik_id') or None
        date_str = data.get('date') or str(date.today())
        linia = data.get('linia') or 'AGRO'
    else:
        note = request.form.get('note', '').strip()
        pracownik_id = request.form.get('pracownik_id') or None
        date_str = request.form.get('date') or str(date.today())
        linia = request.form.get('linia') or request.args.get('linia') or 'AGRO'

    author = session.get('login') or 'unknown'
    is_ajax = _is_ajax_request()
    
    current_app.logger.info('add_shift_note: note=%s, pracownik_id=%s, date=%s, author=%s', 
                           note[:50] if note else '', pracownik_id, date_str, author)
    
    conn = None
    nid = None
    try:
        table_notes = get_table_name('shift_notes', linia)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_notes} (
                    id BIGINT PRIMARY KEY,
                    pracownik_id INT,
                    note TEXT,
                    author VARCHAR(255),
                    date DATE,
                    created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    linia VARCHAR(20) DEFAULT '{linia}'
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
        except Exception as e:
            current_app.logger.debug(f'CREATE TABLE {table_notes}: {e}')
        
        nid = int(time.time() * 1000)  # Use milliseconds for uniqueness
        cursor.execute(f"INSERT INTO {table_notes} (id, pracownik_id, note, author, date, linia) VALUES (%s, %s, %s, %s, %s, %s)", 
                      (nid, pracownik_id, note, author, date_str, linia))
        conn.commit()
        current_app.logger.info('Note saved successfully: id=%s, linia=%s, table=%s', nid, linia, table_notes)
        if not is_ajax:
            flash('✅ Notatka zapisana', 'success')
        else:
            return jsonify({
                'success': True,
                'id': nid,
                'note': note,
                'author': author,
                'date': date_str,
                'message': 'Notatka zapisana automatycznie'
            })
    
    except Exception as e:
        current_app.logger.error(f'Failed to save shift note: {e}', exc_info=True)
        try:
            conn.rollback()
        except Exception:
            pass
        if is_ajax:
            return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    
    # Bezpieczny powrót na stronę wywołującą (np. Dashboard AGRO)
    target_url = request.referrer or url_for('main.index', linia=linia, data=date_str)
    return redirect(target_url)


@shifts_bp.route('/api/shift_note/<int:note_id>/delete', methods=['POST'])
@login_required
def delete_shift_note(note_id):
    """Delete a shift note (author leader or admin/masteradmin only)."""
    is_ajax = _is_ajax_request()
    if request.is_json:
        data = request.get_json(silent=True) or {}
        linia = data.get('linia') or 'AGRO'
    else:
        linia = request.form.get('linia') or request.args.get('linia') or 'AGRO'

    conn = None
    try:
        table_notes = get_table_name('shift_notes', linia)
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(f"SELECT author FROM {table_notes} WHERE id = %s", (note_id,))
        row = cursor.fetchone()
        if not row:
            cursor.execute("SELECT author FROM shift_notes WHERE id = %s", (note_id,))
            row = cursor.fetchone()
        
        login_u = session.get('login') or ''
        name_u = session.get('imie_nazwisko') or ''
        rola = str(session.get('rola') or '').lower().strip()
        
        is_admin = rola in ['admin', 'masteradmin']
        is_author_leader = rola == 'lider' and row and (row[0] == login_u or row[0] == name_u)
        
        if is_admin or is_author_leader:
            try:
                cursor.execute(f"DELETE FROM {table_notes} WHERE id = %s", (note_id,))
            except Exception:
                pass
            cursor.execute("DELETE FROM shift_notes WHERE id = %s", (note_id,))
            conn.commit()
            current_app.logger.info('Shift note deleted: id=%s, user=%s', note_id, login_u)
            if is_ajax:
                return jsonify({'success': True, 'id': note_id, 'message': 'Notatka usunięta'})
            flash('✅ Notatka usunięta', 'success')
        else:
            current_app.logger.warning('Unauthorized delete attempt: id=%s, user=%s', note_id, login_u)
            if is_ajax:
                return jsonify({'success': False, 'message': 'Brak uprawnień do usunięcia notatki'}), 403
            flash('❌ Brak uprawnień do usunięcia notatki', 'danger')
    
    except Exception as e:
        current_app.logger.error(f'Error deleting shift note {note_id}: {e}', exc_info=True)
        try:
            conn.rollback()
        except Exception:
            pass
        if is_ajax:
            return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    
    target_url = request.referrer or url_for('main.index', linia=linia)
    return redirect(target_url)


@shifts_bp.route('/api/shift_note/<int:note_id>/update', methods=['POST'])
@login_required
def update_shift_note(note_id):
    """Edit a shift note (author leader or admin/masteradmin only)."""
    is_ajax = _is_ajax_request()
    if request.is_json:
        data = request.get_json(silent=True) or {}
        note_text = data.get('note', '').strip()
        linia = data.get('linia') or 'AGRO'
    else:
        note_text = request.form.get('note', '').strip()
        linia = request.form.get('linia') or request.args.get('linia') or 'AGRO'

    conn = None
    try:
        table_notes = get_table_name('shift_notes', linia)
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(f"SELECT author FROM {table_notes} WHERE id = %s", (note_id,))
        row = cursor.fetchone()
        if not row:
            cursor.execute("SELECT author FROM shift_notes WHERE id = %s", (note_id,))
            row = cursor.fetchone()
            
        login_u = session.get('login') or ''
        name_u = session.get('imie_nazwisko') or ''
        rola = str(session.get('rola') or '').lower().strip()
        
        is_admin = rola in ['admin', 'masteradmin']
        is_author_leader = rola == 'lider' and row and (row[0] == login_u or row[0] == name_u)
        
        if is_admin or is_author_leader:
            try:
                cursor.execute(f"UPDATE {table_notes} SET note = %s WHERE id = %s", (note_text, note_id))
            except Exception:
                pass
            cursor.execute("UPDATE shift_notes SET note = %s WHERE id = %s", (note_text, note_id))
            conn.commit()
            current_app.logger.info('Shift note updated: id=%s, user=%s', note_id, login_u)
            if is_ajax:
                return jsonify({'success': True, 'id': note_id, 'note': note_text, 'message': 'Notatka zaktualizowana'})
            flash('✅ Notatka zaktualizowana', 'success')
        else:
            current_app.logger.warning('Unauthorized update attempt: id=%s, user=%s', note_id, login_u)
            if is_ajax:
                return jsonify({'success': False, 'message': 'Brak uprawnień do edycji notatki'}), 403
            flash('❌ Brak uprawnień do edycji notatki', 'danger')
    
    except Exception as e:
        current_app.logger.error(f'Error updating shift note {note_id}: {e}', exc_info=True)
        try:
            conn.rollback()
        except Exception:
            pass
        if is_ajax:
            return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    
    target_url = request.referrer or url_for('main.index', linia=linia)
    return redirect(target_url)


