"""Shift notes routes."""

from flask import Blueprint, request, redirect, flash, session, current_app
from datetime import date
import time

from app.decorators import login_required, roles_required
from app.db import get_db_connection

shifts_bp = Blueprint('shifts', __name__)


@shifts_bp.route('/add_shift_note', methods=['POST'])
@login_required
def add_shift_note():
    """Create a new shift note."""
    try:
        note = request.form.get('note', '').strip()
        pracownik_id = request.form.get('pracownik_id') or None
        date_str = request.form.get('date') or str(date.today())
        author = session.get('login') or 'unknown'

        current_app.logger.info('add_shift_note: note=%s, pracownik_id=%s, date=%s, author=%s', note[:50] if note else '', pracownik_id, date_str, author)

        # Ensure shift_notes table exists and insert record
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS shift_notes (
                    id BIGINT PRIMARY KEY,
                    pracownik_id INT,
                    note TEXT,
                    author VARCHAR(255),
                    date DATE,
                    created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
        except Exception:
            # ignore create table errors
            pass
        nid = int(time.time() * 1000)  # Use milliseconds for uniqueness
        try:
            cursor.execute("INSERT INTO shift_notes (id, pracownik_id, note, author, date) VALUES (%s, %s, %s, %s, %s)", (nid, pracownik_id, note, author, date_str))
            conn.commit()
            current_app.logger.info('Note saved successfully: id=%s', nid)
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            current_app.logger.exception('Failed to insert shift note into DB: %s', str(e))
        try:
            conn.close()
        except Exception:
            pass
        try:
            flash('✅ Notatka zapisana', 'success')
        except Exception:
            pass
    except Exception:
        try:
            current_app.logger.exception('Error in add_shift_note')
        except Exception:
            pass
    return redirect('/')


@shifts_bp.route('/api/shift_note/<int:note_id>/delete', methods=['POST'])
@login_required
@roles_required('lider', 'admin')
def delete_shift_note(note_id):
    """Delete a shift note (owner or admin only)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Sprawdź czy notatka należy do zalogowanego użytkownika lub jest admin
        cursor.execute("SELECT author FROM shift_notes WHERE id = %s", (note_id,))
        row = cursor.fetchone()
        author = session.get('login') or 'unknown'
        if row and (row[0] == author or session.get('rola') == 'admin'):
            cursor.execute("DELETE FROM shift_notes WHERE id = %s", (note_id,))
            conn.commit()
            try:
                flash('Notatka usunięta', 'success')
            except Exception:
                pass
        else:
            try:
                flash('Brak uprawnień do usunięcia notatki', 'danger')
            except Exception:
                pass
        conn.close()
    except Exception:
        try:
            current_app.logger.exception('Error deleting shift note')
        except Exception:
            pass
    return redirect('/')


@shifts_bp.route('/api/shift_note/<int:note_id>/update', methods=['POST'])
@login_required
@roles_required('lider', 'admin')
def update_shift_note(note_id):
    """Edit a shift note (owner or admin only)."""
    try:
        note_text = request.form.get('note', '').strip()
        conn = get_db_connection()
        cursor = conn.cursor()
        # Sprawdź czy notatka należy do zalogowanego użytkownika lub jest admin
        cursor.execute("SELECT author FROM shift_notes WHERE id = %s", (note_id,))
        row = cursor.fetchone()
        author = session.get('login') or 'unknown'
        if row and (row[0] == author or session.get('rola') == 'admin'):
            cursor.execute("UPDATE shift_notes SET note = %s WHERE id = %s", (note_text, note_id))
            conn.commit()
            try:
                flash('Notatka zaktualizowana', 'success')
            except Exception:
                pass
        else:
            try:
                flash('Brak uprawnień do edycji notatki', 'danger')
            except Exception:
                pass
        conn.close()
    except Exception:
        try:
            current_app.logger.exception('Error updating shift note')
        except Exception:
            pass
    return redirect('/')

