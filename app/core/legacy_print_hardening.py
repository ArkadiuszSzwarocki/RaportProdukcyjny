"""Runtime replacements for legacy print paths that cannot be safely removed at once.

The project still contains large legacy blueprints. This module replaces risky
transport boundaries after blueprints are registered, keeping URL/endpoint
compatibility while routing supported jobs through the authenticated, DB-backed
print queue.
"""

from flask import jsonify, redirect, request, url_for

from app.core.database import get_db_connection
from app.services.print_server import get_printer
from app.utils.pallet_label import prepare_pallet_label_data


def _bounded_copies(value):
    try:
        return max(1, min(20, int(value or 2)))
    except (TypeError, ValueError):
        return 2


def _requested_pallets(payload):
    """Return unique pallet references and optional line hints from a request."""
    raw_items = payload.get('items')
    source_items = raw_items if isinstance(raw_items, list) and raw_items else [payload]
    result = []
    seen = set()
    for item in source_items[:100]:
        if not isinstance(item, dict):
            continue
        reference = item.get('nr_palety') or item.get('nrPalety') or item.get('sscc')
        reference = str(reference or '').strip()
        if not reference or reference in ('-', '---') or reference in seen:
            continue
        seen.add(reference)
        line = str(item.get('linia') or payload.get('linia') or '').strip().upper()
        result.append((reference, line))
    return result


def _load_authoritative_label(cursor, pallet_ref, line_hint=''):
    """Load a pallet label from DB instead of trusting browser-provided fields."""
    candidates = []
    for line in (line_hint, 'PSD', 'AGRO'):
        line = str(line or '').strip().upper()
        if line and line not in candidates:
            candidates.append(line)

    for line in candidates:
        try:
            data = prepare_pallet_label_data(cursor, pallet_ref, linia=line)
        except Exception:
            data = None
        if data:
            if not data.get('linia'):
                data['linia'] = line
            return data
    return None


def secure_reprint_labels():
    """Secure replacement for ``magazyn_dostawy.dodruk_etykiet``.

    The blueprint's existing before_request authentication still applies. The
    replacement validates the printer against the DB, reloads pallet data from
    the DB, bounds batch/copy sizes, and queues jobs instead of spawning a
    fire-and-forget HTTP thread to the bridge.
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'success': False, 'error': 'Wymagany obiekt JSON.'}), 400

    printer_id = payload.get('printer_id')
    try:
        printer_id = int(printer_id)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Wybierz poprawną drukarkę.'}), 400

    pallet_refs = _requested_pallets(payload)
    if not pallet_refs:
        return jsonify({'success': False, 'error': 'Brak numeru palety do dodruku.'}), 400

    copies = _bounded_copies(payload.get('copies'))
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            'SELECT ip, nazwa FROM drukarki WHERE id = %s AND aktywna = 1 LIMIT 1',
            (printer_id,),
        )
        printer_row = cursor.fetchone()
        if not printer_row:
            return jsonify({'success': False, 'error': 'Drukarka nie istnieje lub jest nieaktywna.'}), 404

        authoritative = []
        missing = []
        for pallet_ref, line_hint in pallet_refs:
            label_data = _load_authoritative_label(cursor, pallet_ref, line_hint)
            if label_data:
                authoritative.append(label_data)
            else:
                missing.append(pallet_ref)
    finally:
        conn.close()

    if not authoritative:
        return jsonify({
            'success': False,
            'error': 'Nie znaleziono wskazanych palet w aktywnym magazynie.',
            'missing': missing,
        }), 404

    printer = get_printer()
    queued = 0
    failures = []
    target_ip = str(printer_row.get('ip') or '').strip()
    target_name = str(printer_row.get('nazwa') or '').strip()

    for label_data in authoritative:
        try:
            zpl = printer.build_pallet_label_zpl(label_data, copies=copies)
            ok, message = printer.queue_print_job(
                zpl,
                override_ip=target_ip or None,
                override_name=target_name or None,
            )
            if ok:
                queued += 1
            else:
                failures.append(message)
        except Exception as exc:
            failures.append(str(exc))

    if queued == 0:
        return jsonify({
            'success': False,
            'error': 'Nie udało się zakolejkować wydruku.',
            'details': failures[:5],
        }), 500

    response = {
        'success': True,
        'count': queued,
        'copies': copies,
        'message': f'Zakolejkowano {queued * copies} etykiet ({queued} palet po {copies} szt.).',
    }
    if missing:
        response['missing'] = missing
        response['warning'] = 'Część wskazanych palet nie została odnaleziona i nie została wydrukowana.'
    if failures:
        response['failed_jobs'] = len(failures)
    return jsonify(response)


def secure_admin_zpl_test():
    """Disable the legacy arbitrary-IP raw socket printer diagnostic.

    The old master-admin test page accepted an arbitrary host and opened TCP
    port 9100 directly from the application server. All printing must instead
    use configured printers and the authenticated queue/bridge path.
    """
    if request.method == 'GET':
        return redirect(url_for('admin.admin_ustawienia_drukarki'))
    return jsonify({
        'success': False,
        'message': (
            'Bezpośredni test IP został wyłączony. '
            'Użyj skonfigurowanej drukarki z panelu ustawień.'
        ),
    }), 410


def secure_admin_printer_server_status():
    """Check the bridge through the authenticated/TLS-validating client."""
    ok, message = get_printer().test_connection()
    return jsonify({
        'success': True,
        'running': bool(ok),
        'message': message,
    })


def _secure_legacy_bridge_request(method, path, timeout):
    """Route old printer start/stop helpers through the authenticated client."""
    printer = get_printer()
    response, _ = printer._request_bridge(  # pylint: disable=protected-access
        method,
        path,
        timeout=timeout,
    )
    return response


def register_legacy_print_hardening(app):
    """Install secure transports without changing existing public URLs."""
    replacements = {
        'magazyn_dostawy.dodruk_etykiet': secure_reprint_labels,
        'admin.admin_zpl_test': secure_admin_zpl_test,
        'admin.admin_printer_server_status': secure_admin_printer_server_status,
    }
    for endpoint, replacement in replacements.items():
        if endpoint in app.view_functions:
            app.view_functions[endpoint] = replacement

    # auth.base still contains legacy local helper code for printer service
    # administration. Replace its network boundary so requests use the same
    # token/TLS policy as every other bridge call.
    try:
        from app.blueprints.auth import base as auth_base
        auth_base._request_bridge = _secure_legacy_bridge_request
    except Exception as exc:
        app.logger.warning('Could not harden legacy printer helper: %s', exc)
