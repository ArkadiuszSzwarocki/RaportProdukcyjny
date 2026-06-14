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
    Attempts to print the PDF.
    First, it checks if it's an IP address. If so, it tries Port 9100 Direct PDF printing.
    If it's a name or 9100 fails, it tries using PowerShell / SumatraPDF if available,
    or win32api as fallback.
    """
    # Check if IP
    import re
    is_ip = re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", printer_name_or_ip)
    
    if is_ip:
        print(f"[OFFICE_PRINT] Attempting raw TCP (Port 9100) print to {printer_name_or_ip}")
        try:
            with open(pdf_path, 'rb') as f:
                pdf_data = f.read()
            with socket.create_connection((printer_name_or_ip, 9100), timeout=5) as s:
                s.sendall(pdf_data)
            print("[OFFICE_PRINT] Raw TCP print successful.")
            return
        except Exception as e:
            print(f"[OFFICE_PRINT] Raw TCP failed: {e}. Falling back to system print.")

    # System Print Fallback
    try:
        import win32api
        import win32print
        import win32ui
        import fitz
        from PIL import Image, ImageWin
        
        # If it's not an IP, assume it's the exact printer name
        printer = printer_name_or_ip if not is_ip else win32print.GetDefaultPrinter()
        print(f"[OFFICE_PRINT] Using PyMuPDF + win32ui with printer: {printer}")
        
        # Open PDF with PyMuPDF
        doc = fitz.open(pdf_path)
        
        # Setup printer Device Context
        hDC = win32ui.CreateDC()
        hDC.CreatePrinterDC(printer)
        
        # Physical printable area dimensions
        printable_width = hDC.GetDeviceCaps(8)  # HORZRES
        printable_height = hDC.GetDeviceCaps(10) # VERTRES
        
        hDC.StartDoc("Raport Produkcyjny")
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            # Render page to an image (scale matrix 2.0 for higher DPI)
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            
            # Convert to PIL Image
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            # Ensure correct orientation
            if img.size[0] > img.size[1]:
                img = img.rotate(90, expand=True)
                
            # Scale to fit printable area
            ratios = [1.0 * printable_width / img.size[0], 1.0 * printable_height / img.size[1]]
            scale = min(ratios)
            
            hDC.StartPage()
            
            dib = ImageWin.Dib(img)
            scaled_width, scaled_height = [int(scale * i) for i in img.size]
            
            # Center the image on the page
            x1 = int((printable_width - scaled_width) / 2)
            y1 = int((printable_height - scaled_height) / 2)
            x2 = x1 + scaled_width
            y2 = y1 + scaled_height
            
            dib.draw(hDC.GetHandleOutput(), (x1, y1, x2, y2))
            
            hDC.EndPage()
            
        hDC.EndDoc()
        hDC.DeleteDC()
        doc.close()
        print("[OFFICE_PRINT] Silent print successful.")
        
        # Wait a bit before deleting
        time.sleep(2)
        
    except Exception as e:
        print(f"[OFFICE_PRINT] PyMuPDF print failed: {e}. Falling back to ShellExecute.")
        try:
            import win32api
            import win32print
            printer = printer_name_or_ip if not is_ip else win32print.GetDefaultPrinter()
            win32api.ShellExecute(0, "printto", pdf_path, f'"{printer}"', ".", 0)
            time.sleep(5)
        except Exception as ex:
            import subprocess
            subprocess.run(["powershell", "-command", f"Start-Process -FilePath '{pdf_path}' -Verb Print -PassThru | %{{sleep 5;$_}} | stop-process"])

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
