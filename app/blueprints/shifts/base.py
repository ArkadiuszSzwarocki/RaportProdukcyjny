"""Shift notes routes."""

from flask import Blueprint, request, redirect, flash, session, current_app
from datetime import date
import time

from app.decorators import login_required, roles_required, masteradmin_required
from app.db import get_db_connection, get_table_name

shifts_bp = Blueprint('shifts', __name__)


@shifts_bp.route('/add_shift_note', methods=['POST'])
@login_required
def add_shift_note():
    """Create a new shift note."""
    note = request.form.get('note', '').strip()
    pracownik_id = request.form.get('pracownik_id') or None
    date_str = request.form.get('date') or str(date.today())
    author = session.get('login') or 'unknown'
    
    current_app.logger.info('add_shift_note: note=%s, pracownik_id=%s, date=%s, author=%s', 
                           note[:50] if note else '', pracownik_id, date_str, author)
    
    conn = None
    try:
        linia = request.form.get('linia') or request.args.get('linia') or 'AGRO'
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
        flash('✅ Notatka zapisana', 'success')
    
    except Exception as e:
        current_app.logger.error(f'Failed to save shift note: {e}', exc_info=True)
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    
    # Bezpieczny powrót na stronę wywołującą (np. Dashboard AGRO)
    target_url = request.referrer or url_for('main.index', linia=request.form.get('linia') or 'AGRO', data=date_str)
    return redirect(target_url)


@shifts_bp.route('/api/shift_note/<int:note_id>/delete', methods=['POST'])
@login_required
def delete_shift_note(note_id):
    """Delete a shift note (author leader or admin/masteradmin only)."""
    conn = None
    try:
        linia = request.form.get('linia') or request.args.get('linia') or 'AGRO'
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
            flash('✅ Notatka usunięta', 'success')
            current_app.logger.info('Shift note deleted: id=%s, user=%s', note_id, login_u)
        else:
            flash('❌ Brak uprawnień do usunięcia notatki', 'danger')
            current_app.logger.warning('Unauthorized delete attempt: id=%s, user=%s', note_id, login_u)
    
    except Exception as e:
        current_app.logger.error(f'Error deleting shift note {note_id}: {e}', exc_info=True)
        try:
            conn.rollback()
        except Exception:
            pass
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
    conn = None
    try:
        linia = request.form.get('linia') or request.args.get('linia') or 'AGRO'
        table_notes = get_table_name('shift_notes', linia)
        note_text = request.form.get('note', '').strip()
        
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
            flash('✅ Notatka zaktualizowana', 'success')
            current_app.logger.info('Shift note updated: id=%s, user=%s', note_id, login_u)
        else:
            flash('❌ Brak uprawnień do edycji notatki', 'danger')
            current_app.logger.warning('Unauthorized update attempt: id=%s, user=%s', note_id, login_u)
    
    except Exception as e:
        current_app.logger.error(f'Error updating shift note {note_id}: {e}', exc_info=True)
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    
    target_url = request.referrer or url_for('main.index', linia=linia)
    return redirect(target_url)


