"""Bounded, authenticated office report rendering and printing."""

import os
import tempfile
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from flask import current_app


_PRINT_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix='office-print')


def _local_report_url(report_url: str) -> tuple[str, dict]:
    """Return a loopback report URL and header-only short-lived auth token."""
    parsed = urllib.parse.urlparse(report_url)
    path = parsed.path or '/'
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    # Credentials must not be present in browser history, access logs or referrers.
    query.pop('print_token', None)
    query.setdefault('internal_print', ['1'])
    encoded_query = urllib.parse.urlencode(query, doseq=True)

    protocol = 'https' if str(os.environ.get('USE_SSL', 'false')).lower() == 'true' else 'http'
    normalized = parsed._replace(
        scheme=protocol,
        netloc='127.0.0.1:8082',
        query=encoded_query,
    ).geturl()

    from app.utils.security_tokens import generate_internal_print_token
    token = generate_internal_print_token(path)
    return normalized, {'X-Internal-Print-Token': token}


def _render_pdf(report_url: str, pdf_path: str) -> None:
    from playwright.sync_api import sync_playwright

    target_url, auth_headers = _local_report_url(report_url)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--no-proxy-server'])
        try:
            context = browser.new_context(
                ignore_https_errors=False,
                extra_http_headers=auth_headers,
            )
            page = context.new_page()
            response = page.goto(target_url, wait_until='networkidle')
            if response is not None and response.status >= 400:
                raise RuntimeError(f'Render endpoint returned HTTP {response.status}')
            page.wait_for_timeout(700)
            page.pdf(
                path=pdf_path,
                format='A4',
                print_background=True,
                margin={
                    'top': '10mm',
                    'right': '10mm',
                    'bottom': '10mm',
                    'left': '10mm',
                },
            )
        finally:
            browser.close()


def _print_pdf(pdf_path: str, printer_name_or_ip: str) -> None:
    """Send PDF through the authenticated bridge client."""
    from app.services.print_server import get_printer

    printer = get_printer()
    if hasattr(printer, '_ensure_bridge_running'):
        printer._ensure_bridge_running()

    with open(pdf_path, 'rb') as handle:
        files = {'file': (os.path.basename(pdf_path), handle, 'application/pdf')}
        data = {'drukarka': printer_name_or_ip}
        response, _ = printer._request_bridge(  # pylint: disable=protected-access
            'POST',
            '/drukuj-pdf',
            files=files,
            data=data,
            timeout=(printer.bridge_connect_timeout, max(printer.bridge_read_timeout, 30)),
        )

    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code != 200 or not body.get('success'):
        raise RuntimeError(body.get('message') or f'Print bridge HTTP {response.status_code}')


def _generate_and_print_url(report_url: str, printer_name_or_ip: str, prefix: str = 'raport_') -> None:
    fd, pdf_path = tempfile.mkstemp(suffix='.pdf', prefix=prefix)
    os.close(fd)
    try:
        _render_pdf(report_url, pdf_path)
        _print_pdf(pdf_path, printer_name_or_ip)
    except Exception:
        try:
            current_app.logger.exception('Office print failed for %s', report_url)
        except Exception:
            pass
    finally:
        try:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
        except OSError:
            pass


def _generate_and_print_plan(plan_id, printer_name_or_ip):
    report_url = f'http://127.0.0.1:8082/agro/raport_palet?plan_id={int(plan_id)}'
    _generate_and_print_url(report_url, printer_name_or_ip, prefix=f'raport_zlecenia_{plan_id}_')


def _printer_assignment(typ_raportu: str):
    from app.db import get_db_connection

    conn = get_db_connection()
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            'SELECT nazwa_drukarki FROM przypisania_raportow '
            'WHERE aktywne = 1 AND typ_raportu = %s LIMIT 1',
            (typ_raportu,),
        )
        row = cursor.fetchone()
        if not row or not row.get('nazwa_drukarki'):
            return None
        return str(row['nazwa_drukarki']).strip() or None
    finally:
        if cursor:
            cursor.close()
        conn.close()


def trigger_office_print(plan_id, typ_raportu='raport_palet_agro'):
    """Queue one report generation job in a bounded executor."""
    try:
        printer_target = _printer_assignment(typ_raportu)
        if not printer_target:
            return False
        _PRINT_EXECUTOR.submit(_generate_and_print_plan, int(plan_id), printer_target)
        return True
    except Exception:
        try:
            current_app.logger.exception('Could not queue office print for plan %s', plan_id)
        except Exception:
            pass
        return False


def trigger_office_print_url(report_url, typ_raportu='raport_palet_agro', prefix='raport_'):
    """Queue a URL render job after validating that it targets this application."""
    try:
        parsed = urllib.parse.urlparse(str(report_url or ''))
        if not parsed.path.startswith('/'):
            return False
        # The supplied network location is intentionally discarded by
        # _local_report_url; only path/query identify the local report.
        printer_target = _printer_assignment(typ_raportu)
        if not printer_target:
            return False
        _PRINT_EXECUTOR.submit(
            _generate_and_print_url,
            str(report_url),
            printer_target,
            prefix,
        )
        return True
    except Exception:
        try:
            current_app.logger.exception('Could not queue office print URL')
        except Exception:
            pass
        return False
