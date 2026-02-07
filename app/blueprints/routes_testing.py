"""Test and development endpoints (formerly routes_api.py TEST ENDPOINTS section)."""

from flask import Blueprint, request, jsonify, render_template, send_file, current_app
from flask import current_app as app
from datetime import datetime, date
from io import BytesIO
import zipfile
import os
import sys

testing_bp = Blueprint('testing', __name__, url_prefix='/test')


@testing_bp.route('/download-page')
def test_download_page():
    """Strona testowa do pobrania raportów"""
    return render_template('test_download.html')


@testing_bp.route('/generate-report')
def test_generate_report():
    """Test endpoint - Wygeneruj raport bez pobierania"""
    try:
        data_str = request.args.get('data') or str(date.today())
        
        print(f"\n[TEST-GENERATE] Starting report generation for {data_str}")
        sys.stdout.flush()
        
        # Import generator
        try:
            from generator_raportow import generuj_paczke_raportow
        except ImportError:
            return jsonify({
                "success": False,
                "error": "Report generator not available",
                "message": "Generator raportów niedostępny"
            }), 503
        
        # Generate reports
        xls_path, txt_path, pdf_path = generuj_paczke_raportow(data_str, "Test raport", "Admin")
        
        # Check if files exist
        xls_exists = os.path.exists(xls_path) if xls_path else False
        txt_exists = os.path.exists(txt_path) if txt_path else False
        pdf_exists = os.path.exists(pdf_path) if pdf_path else False
        
        print(f"[TEST-GENERATE] XLS: {xls_path} (exists={xls_exists})")
        print(f"[TEST-GENERATE] TXT: {txt_path} (exists={txt_exists})")
        print(f"[TEST-GENERATE] PDF: {pdf_path} (exists={pdf_exists})")
        sys.stdout.flush()
        
        return jsonify({
            "success": True,
            "message": f"OK Raport wygenerowany dla {data_str}",
            "xls": xls_path,
            "xls_exists": xls_exists,
            "txt": txt_path,
            "txt_exists": txt_exists,
            "pdf": pdf_path,
            "pdf_exists": pdf_exists
        }), 200
        
    except Exception as e:
        print(f"[TEST-GENERATE] ERROR: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.stderr.flush()
        
        return jsonify({
            "success": False,
            "error": str(e),
            "message": f"ERROR Blad: {str(e)}"
        }), 500


@testing_bp.route('/download-zip')
def test_download_zip():
    """Test endpoint - Zwróć prosty ZIP do pobrania"""
    try:
        data_str = request.args.get('data') or str(date.today())
        
        print(f"\n[TEST-ZIP] Starting ZIP creation for {data_str}")
        sys.stdout.flush()
        
        # Create test ZIP with dummy file
        zip_buffer = BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Add test file
            test_content = f"Test raport dla daty: {data_str}\nGodzina: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            zip_file.writestr("test_raport.txt", test_content)
            
            # Try to add real reports if they exist
            raporty_dir = 'raporty'
            if os.path.exists(raporty_dir):
                for file in os.listdir(raporty_dir):
                    if data_str in file and file.endswith(('.xlsx', '.txt', '.pdf')):
                        file_path = os.path.join(raporty_dir, file)
                        zip_file.write(file_path, arcname=file)
                        print(f"[TEST-ZIP] Added: {file}")
                        sys.stdout.flush()
        
        zip_buffer.seek(0)
        
        print(f"[TEST-ZIP] ZIP created, size: {len(zip_buffer.getvalue())} bytes")
        sys.stdout.flush()
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f"Test_Raporty_{data_str}.zip"
        )
        
    except Exception as e:
        print(f"[TEST-ZIP] ERROR: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.stderr.flush()
        
        return jsonify({
            "success": False,
            "error": str(e),
            "message": f"ERROR Blad: {str(e)}"
        }), 500

