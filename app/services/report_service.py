"""
Report generation and ZIP download service.
Handles the complete workflow of generating reports (XLS, TXT, PDF) and creating a downloadable ZIP file.
"""

import os
import zipfile
from io import BytesIO
from datetime import datetime, timedelta, date

from app.db import get_db_connection
from scripts.generator_raportow import generuj_paczke_raportow
from flask import current_app


def load_shift_notes(date_obj):
    """
    Load shift notes for a given date.
    
    Args:
        date_obj: datetime.date object
        
    Returns:
        tuple: (uwagi_string, success_flag)
    """
    uwagi = ""
    try:
        conn_notes = get_db_connection()
        cursor_notes = conn_notes.cursor(dictionary=True)
        
        query_notes = "SELECT note, author, created FROM shift_notes WHERE DATE(created) = %s ORDER BY created ASC"
        date_param = date_obj.strftime('%Y-%m-%d')
        current_app.logger.debug(f"[REPORT_SERVICE] Executing query with date={date_param}")
        cursor_notes.execute(query_notes, (date_param,))
        notes = cursor_notes.fetchall()
        cursor_notes.close()
        conn_notes.close()
        
        current_app.logger.debug(f"[REPORT_SERVICE] Query result - notes count: {len(notes)}")
        if notes:
            current_app.logger.debug(f"[REPORT_SERVICE] OK Loaded {len(notes)} shift notes from database")
            # Format notes
            uwagi = "NOTATKI ZMIANOWE:\n" + "-" * 50 + "\n"
            for i, note in enumerate(notes):
                created_time = note['created'].strftime('%H:%M:%S') if note['created'] else '??:??:??'
                uwagi += f"\n[{created_time}] {note['author']}:\n{note['note']}\n"
                current_app.logger.debug(f"[REPORT_SERVICE] Note {i+1}: author={note['author']}, time={created_time}")
        else:
            current_app.logger.warning(f"[REPORT_SERVICE] WARNING No shift notes found for {date_param}")
            uwagi = ""
    except Exception as e:
        current_app.logger.error(f"[REPORT_SERVICE] ERROR Error loading shift notes: {e}")
        import traceback
        traceback.print_exc()
        uwagi = ""
    
    current_app.logger.debug(f"[REPORT_SERVICE] Final notes length: {len(uwagi)} chars")
    return uwagi


def get_leader_name(session_data, form_data):
    """
    Get leader name from session or form data.
    
    Args:
        session_data: dict with session info (pracownik_id, login)
        form_data: dict with form info (lider_id, lider_prowadzacy_id)
        
    Returns:
        tuple: (lider_name, uwagi_additions)
    """
    lider_name = "Nieznany"
    uwagi_addition = ""
    
    try:
        pracownik_id = session_data.get('pracownik_id')
        lider_login = session_data.get('login', 'nieznany')
        form_lider_id = form_data.get('lider_id')
        form_lider_prowadzacy_id = form_data.get('lider_prowadzacy_id')

        current_app.logger.debug(f"[REPORT_SERVICE] Looking for lider: session_pracownik_id={pracownik_id}, form_lider_id={form_lider_id}")

        conn_user = get_db_connection()
        cursor_user = conn_user.cursor()
        
        # Get main leader name
        chosen_lider_id = form_lider_id if form_lider_id else pracownik_id
        if chosen_lider_id:
            cursor_user.execute("SELECT imie_nazwisko FROM pracownicy WHERE id = %s", (chosen_lider_id,))
            row = cursor_user.fetchone()
            if row and row[0]:
                lider_name = row[0]
                current_app.logger.debug(f"[REPORT_SERVICE] OK Found lider name: {lider_name} (id={chosen_lider_id})")
        else:
            lider_name = lider_login

        # Get leader prowadzacy name if provided
        if form_lider_prowadzacy_id:
            cursor_user.execute("SELECT imie_nazwisko FROM pracownicy WHERE id = %s", (form_lider_prowadzacy_id,))
            row2 = cursor_user.fetchone()
            if row2 and row2[0]:
                prowadzacy_name = row2[0]
                uwagi_addition = f"\nLider prowadzacy: {prowadzacy_name}\n"
                current_app.logger.debug(f"[REPORT_SERVICE] OK Lider prowadzacy: {prowadzacy_name} (id={form_lider_prowadzacy_id})")

        cursor_user.close()
        conn_user.close()
    except Exception as e:
        current_app.logger.error(f"[REPORT_SERVICE] ERROR Error fetching leader names: {e}")
        import traceback
        traceback.print_exc()
    
    return lider_name, uwagi_addition


def generate_reports(date_str, uwagi, lider_name):
    """
    Generate reports using the report generator.
    
    Args:
        date_str: string in format YYYY-MM-DD
        uwagi: string with notes/comments
        lider_name: name of the leader
        
    Returns:
        tuple: (xls_path, txt_path, pdf_path) or raises exception
    """
    current_app.logger.debug(f"[REPORT_SERVICE] Calling generator with date={date_str}, lider={lider_name}, uwagi_len={len(uwagi)}")
    
    try:
        xls_path, txt_path, pdf_path = generuj_paczke_raportow(date_str, uwagi, lider_name)
        current_app.logger.debug(f"[REPORT_SERVICE] OK Reports generated successfully!")
        current_app.logger.debug(f"[REPORT_SERVICE] Excel: {xls_path} | exists={os.path.exists(xls_path) if xls_path else False}")
        current_app.logger.debug(f"[REPORT_SERVICE] TXT: {txt_path} | exists={os.path.exists(txt_path) if txt_path else False}")
        current_app.logger.debug(f"[REPORT_SERVICE] PDF: {pdf_path} | exists={os.path.exists(pdf_path) if pdf_path else False}")
        return xls_path, txt_path, pdf_path
    except Exception as e:
        current_app.logger.error(f"[REPORT_SERVICE] ERROR GENERATOR FAILED: {e}", exc_info=True)
        raise


def move_files_to_raporty_dir(xls_path, txt_path):
    """
    Move generated files from raporty_temp to raporty directory.
    
    Args:
        xls_path: path to Excel file
        txt_path: path to TXT file
        
    Returns:
        tuple: (final_xls, final_txt)
    """
    import shutil
    
    raporty_dir = 'raporty'
    if not os.path.exists(raporty_dir):
        os.makedirs(raporty_dir)
        current_app.logger.debug(f"[REPORT_SERVICE] Created {raporty_dir} directory")
    
    # Move Excel
    final_xls = xls_path
    if xls_path and os.path.exists(xls_path) and 'raporty_temp' in xls_path:
        try:
            final_xls = os.path.join(raporty_dir, os.path.basename(xls_path))
            shutil.move(xls_path, final_xls)
            current_app.logger.debug(f"[REPORT_SERVICE] OK Moved Excel to {final_xls}")
        except Exception as e:
            current_app.logger.error(f"[REPORT_SERVICE] ERROR Could not move Excel: {e}")
            final_xls = xls_path
    elif xls_path:
        current_app.logger.warning(f"[REPORT_SERVICE] INFO Excel already in correct location: {xls_path}")
    
    # Move TXT
    final_txt = txt_path
    if txt_path and os.path.exists(txt_path) and 'raporty_temp' in txt_path:
        try:
            final_txt = os.path.join(raporty_dir, os.path.basename(txt_path))
            shutil.move(txt_path, final_txt)
            current_app.logger.debug(f"[REPORT_SERVICE] OK Moved TXT to {final_txt}")
        except Exception as e:
            current_app.logger.error(f"[REPORT_SERVICE] ERROR Could not move TXT: {e}")
            final_txt = txt_path
    elif txt_path:
        current_app.logger.warning(f"[REPORT_SERVICE] INFO TXT already in correct location: {txt_path}")
    
    return final_xls, final_txt


def create_zip_archive(final_xls, final_txt, pdf_path, date_str):
    """
    Create a ZIP archive containing all report files.
    
    Args:
        final_xls: path to Excel file
        final_txt: path to TXT file
        pdf_path: path to PDF file
        date_str: date string for filename
        
    Returns:
        tuple: (zip_buffer, zip_filename) or raises exception
    """
    zip_buffer = BytesIO()
    files_added = 0
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Add Excel
        if final_xls and os.path.exists(final_xls):
            zip_file.write(final_xls, arcname=os.path.basename(final_xls))
            current_app.logger.debug(f"[REPORT_SERVICE] OK Added to ZIP: {os.path.basename(final_xls)}")
            files_added += 1
        else:
            current_app.logger.error(f"[REPORT_SERVICE] ERROR Excel file not found: {final_xls}")
        
        # Add TXT
        if final_txt and os.path.exists(final_txt):
            zip_file.write(final_txt, arcname=os.path.basename(final_txt))
            current_app.logger.debug(f"[REPORT_SERVICE] OK Added to ZIP: {os.path.basename(final_txt)}")
            files_added += 1
        else:
            current_app.logger.error(f"[REPORT_SERVICE] ERROR TXT file not found: {final_txt}")
        
        # Add PDF
        if pdf_path and os.path.exists(pdf_path):
            zip_file.write(pdf_path, arcname=os.path.basename(pdf_path))
            current_app.logger.debug(f"[REPORT_SERVICE] OK Added to ZIP: {os.path.basename(pdf_path)}")
            files_added += 1
        else:
            current_app.logger.error(f"[REPORT_SERVICE] ERROR PDF file not found: {pdf_path}")
    
    if files_added == 0:
        raise Exception(f"No files were added to ZIP. XLS: {final_xls}, TXT: {final_txt}, PDF: {pdf_path}")
    
    zip_buffer.seek(0)
    zip_filename = f"Raporty_{date_str}.zip"
    current_app.logger.debug(f"[REPORT_SERVICE] OK ZIP created: {zip_filename} with {files_added} files")
    
    return zip_buffer, zip_filename


def suspend_previous_day_plans(date_obj):
    """
    Suspend all active plans from the previous day.
    
    Args:
        date_obj: datetime.date object for today
    """
    try:
        wczoraj = date_obj - timedelta(days=1)
        wczoraj_param = wczoraj.strftime('%Y-%m-%d')
        
        conn_plans = get_db_connection()
        cursor_plans = conn_plans.cursor()
        
        suspend_query = """
            UPDATE plan_produkcji 
            SET status = 'wstrzymane' 
            WHERE DATE(data_planu) = %s 
            AND status = 'w toku'
        """
        cursor_plans.execute(suspend_query, (wczoraj_param,))
        suspended_count = cursor_plans.rowcount
        conn_plans.commit()
        cursor_plans.close()
        conn_plans.close()
        
        current_app.logger.debug(f"[REPORT_SERVICE] OK Suspended {suspended_count} active plans for {wczoraj_param}")
    except Exception as e:
        current_app.logger.error(f"[REPORT_SERVICE] ERROR Error suspending plans: {e}")
        import traceback
        traceback.print_exc()


def generate_and_download_reports(date_str, uwagi, lider_name):
    """
    Complete workflow: generate reports, create ZIP, prepare for download.
    
    Args:
        date_str: string in format YYYY-MM-DD
        uwagi: string with notes/comments
        lider_name: name of the leader
        
    Returns:
        tuple: (zip_buffer, zip_filename)
        
    Raises:
        Exception: if any step fails
    """
    current_app.logger.debug("[REPORT_SERVICE] ===== REPORT GENERATION WORKFLOW START =====")
    current_app.logger.debug(f"[REPORT_SERVICE] Date: {date_str}, Leader: {lider_name}")
    
    try:
        # Generate reports
        xls_path, txt_path, pdf_path = generate_reports(date_str, uwagi, lider_name)
        
        # Move files to permanent directory
        final_xls, final_txt = move_files_to_raporty_dir(xls_path, txt_path)
        
        # Create ZIP archive
        zip_buffer, zip_filename = create_zip_archive(final_xls, final_txt, pdf_path, date_str)
        
        # Suspend previous day plans
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        suspend_previous_day_plans(date_obj)
        current_app.logger.debug("[REPORT_SERVICE] ===== REPORT GENERATION WORKFLOW COMPLETE =====")
        
        return zip_buffer, zip_filename
        
    except Exception as e:
        current_app.logger.exception(f"[REPORT_SERVICE] EXCEPTION CAUGHT: {str(e)}")
        raise

