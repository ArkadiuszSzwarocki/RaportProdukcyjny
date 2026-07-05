import os
import tempfile
import threading
import time
import socket
import subprocess
from flask import current_app

def _generate_and_print_thread(plan_id, printer_name_or_ip):
    """
    Background thread that generates the report using Playwright,
    and then sends it to the printer.
    """
    # Create a temporary PDF file
    fd, pdf_path = tempfile.mkstemp(suffix=".pdf", prefix=f"raport_zlecenia_{plan_id}_")
    os.close(fd)
    
    try:
        from playwright.sync_api import sync_playwright
        
        # Determine the URL for the report
        # We need to render the report without navbar and extra UI elements.
        # The raport_palet page has CSS for print: @media print.
        report_url = f"http://127.0.0.1:8082/agro/raport_palet?plan_id={plan_id}&internal_print=1"
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            
            # Navigate and wait for network to be idle
            page.goto(report_url, wait_until="networkidle")
            
            # Wait an extra second to ensure any JS rendering is complete
            page.wait_for_timeout(1000)
            
            # Print to PDF
            page.pdf(
                path=pdf_path,
                format="A4",
                print_background=True,
                margin={"top": "10mm", "right": "10mm", "bottom": "10mm", "left": "10mm"}
            )
            
            browser.close()
            
        print(f"[OFFICE_PRINT] PDF generated successfully at: {pdf_path}")
        
        # Now we print it.
        _print_pdf(pdf_path, printer_name_or_ip)
        
    except Exception as e:
        print(f"[OFFICE_PRINT] Error generating/printing PDF: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        try:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
        except Exception as e:
            print(f"[OFFICE_PRINT] Error removing temp file: {e}")

def _print_pdf(pdf_path, printer_name_or_ip):
    """
    Sends the PDF file to the printer server to be printed.
    """
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    try:
        # Import dynamically to avoid circular dependencies if any
        from app.services.print_server import get_printer
        printer = get_printer()
        
        # Ensure the local bridge is running
        if hasattr(printer, '_ensure_bridge_running'):
            printer._ensure_bridge_running()
            
        # Determine bridge URL
        base_url = printer._normalize_bridge_base()
        url = f"{base_url}/drukuj-pdf"
        
        print(f"[OFFICE_PRINT] Sending PDF to printer server: {url} for printer: {printer_name_or_ip}")
        
        with open(pdf_path, 'rb') as f:
            files = {'file': (os.path.basename(pdf_path), f, 'application/pdf')}
            data = {'drukarka': printer_name_or_ip, 'ip': printer_name_or_ip}
            response = requests.post(url, files=files, data=data, verify=False, timeout=30)
            
        try:
            resp_json = response.json()
        except Exception:
            resp_json = {}
            
        if response.status_code == 200 and resp_json.get('success'):
            print("[OFFICE_PRINT] Print successful via printer server.")
        else:
            error_msg = resp_json.get('message', response.text)
            print(f"[OFFICE_PRINT] Printer server returned error: {error_msg}")
    except Exception as e:
        print(f"[OFFICE_PRINT] Failed to send PDF to printer server: {e}")

def trigger_office_print(plan_id, typ_raportu='raport_palet_agro'):
    """
    Triggers the generation and printing of the production report for a given plan_id.
    It looks up the office printer in the database based on the report type.
    """
    from app.db import get_db_connection
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # Find active office printer for this report type
        cursor.execute("SELECT * FROM przypisania_raportow WHERE aktywne = 1 AND typ_raportu = %s LIMIT 1", (typ_raportu,))
        assignment = cursor.fetchone()
        
        if not assignment or not assignment.get('nazwa_drukarki'):
            print(f"[OFFICE_PRINT] No active office printer assigned for report '{typ_raportu}'. Skipping auto-print.")
            return False
            
        printer_target = assignment['nazwa_drukarki'].strip()
        
        # Start background thread
        print(f"[OFFICE_PRINT] Starting background print thread for plan {plan_id} (Report: {typ_raportu}) to {printer_target}")
        t = threading.Thread(target=_generate_and_print_thread, args=(plan_id, printer_target), daemon=True)
        t.start()
        
        return True
    except Exception as e:
        print(f"[OFFICE_PRINT] Error in trigger: {e}")
        return False
        conn.close()

def _generate_and_print_url_thread(report_url, printer_name_or_ip, prefix="raport_"):
    # Force report_url to use 127.0.0.1 to avoid NAT loopback issues with Playwright
    import urllib.parse
    parsed = urllib.parse.urlparse(report_url)
    if parsed.netloc:
        report_url = parsed._replace(netloc="127.0.0.1:8082", scheme="http").geturl()

    fd, pdf_path = tempfile.mkstemp(suffix=".pdf", prefix=prefix)
    os.close(fd)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto(report_url, wait_until="networkidle")
            page.wait_for_timeout(1000)
            page.pdf(
                path=pdf_path,
                format="A4",
                print_background=True,
                margin={"top": "10mm", "right": "10mm", "bottom": "10mm", "left": "10mm"}
            )
            browser.close()
        print(f"[OFFICE_PRINT] PDF generated successfully at: {pdf_path}")
        _print_pdf(pdf_path, printer_name_or_ip)
    except Exception as e:
        print(f"[OFFICE_PRINT] Error generating/printing PDF: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
        except Exception as e:
            print(f"[OFFICE_PRINT] Error removing temp file: {e}")

def trigger_office_print_url(report_url, typ_raportu='raport_palet_agro', prefix="raport_"):
    from app.db import get_db_connection
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM przypisania_raportow WHERE aktywne = 1 AND typ_raportu = %s LIMIT 1", (typ_raportu,))
        assignment = cursor.fetchone()
        
        if not assignment or not assignment.get('nazwa_drukarki'):
            print(f"[OFFICE_PRINT] No active office printer assigned for report '{typ_raportu}'. Skipping auto-print.")
            return False
            
        printer_target = assignment['nazwa_drukarki'].strip()
        print(f"[OFFICE_PRINT] Starting background print thread for {report_url} to {printer_target}")
        t = threading.Thread(target=_generate_and_print_url_thread, args=(report_url, printer_target, prefix), daemon=True)
        t.start()
        return True
    except Exception as e:
        print(f"[OFFICE_PRINT] Error in trigger: {e}")
        return False
    finally:
        conn.close()
