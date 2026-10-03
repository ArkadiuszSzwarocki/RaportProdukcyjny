# cspell:words putaway
"""Runtime replacements for legacy print paths that cannot be safely removed at once.

The project still contains large legacy blueprints and services. This module
replaces risky transport/concurrency boundaries after blueprints are registered,
keeping public API compatibility while routing jobs through the authenticated,
DB-backed print queue.
"""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from flask import jsonify, redirect, request, url_for

from app.core.database import get_db_connection
from app.services.print_server import get_printer
from app.utils.pallet_label import prepare_pallet_label_data


_LEGACY_PRINT_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix='legacy-print')
_ORIGINAL_ACCEPT_ITEM = None


class _ExecutorBackedThread:
    """Tiny Thread-compatible adapter backed by the bounded print executor."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None, **_ignored):
        self._target = target
        self._args = tuple(args or ())
        self._kwargs = dict(kwargs or {})
        self.daemon = daemon
        self._future = None

    def start(self):
        if self._target is None:
            return None
        self._future = _LEGACY_PRINT_EXECUTOR.submit(
            self._target,
            *self._args,
            **self._kwargs,
        )
        return None

    def join(self, timeout=None):
        if self._future is not None:
            return self._future.result(timeout=timeout)
        return None

    def is_alive(self):
        return bool(self._future and not self._future.done())


_BOUNDED_THREADING = SimpleNamespace(Thread=_ExecutorBackedThread)


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
    """Secure replacement for ``magazyn_dostawy.dodruk_etykiet``."""
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


def _queue_accepted_pallet_label(details, requested_ip, requested_name):
    """Queue an accepted-pallet label using only an active DB printer."""
    if not isinstance(details, dict):
        return
    pallet_ref = str(details.get('nr_palety') or '').strip()
    line = str(details.get('linia') or 'PSD').strip().upper()
    if not pallet_ref:
        return

    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        clauses = []
        params = []
        if requested_name:
            clauses.append('nazwa = %s')
            params.append(str(requested_name).strip())
        if requested_ip:
            clauses.append('ip = %s')
            params.append(str(requested_ip).strip())
        if not clauses:
            return
        cursor.execute(
            'SELECT ip, nazwa FROM drukarki WHERE aktywna = 1 AND ('
            + ' OR '.join(clauses)
            + ') ORDER BY id ASC LIMIT 1',
            tuple(params),
        )
        printer_row = cursor.fetchone()
        if not printer_row:
            return
        label_data = _load_authoritative_label(cursor, pallet_ref, line)
    finally:
        conn.close()

    if not label_data:
        return

    printer = get_printer()
    kind = str(label_data.get('typ') or '').lower()
    pallet_upper = pallet_ref.upper()
    is_finished = (
        kind in {'wyrob_gotowy', 'wyrób_gotowy', 'finished', 'gotowy'}
        or pallet_upper.startswith(('PSD', 'AGR', 'WYR'))
    )
    if is_finished:
        zpl = printer.build_finished_product_label_zpl(label_data, copies=2)
    else:
        zpl = printer.build_pallet_label_zpl(label_data, copies=2)
    printer.queue_print_job(
        zpl,
        override_ip=str(printer_row.get('ip') or '').strip() or None,
        override_name=str(printer_row.get('nazwa') or '').strip() or None,
    )


def secure_accept_item(
    dostawa_id,
    item_id,
    lokalizacja,
    login='system',
    nr_partii=None,
    data_produkcji=None,
    data_przydatnosci=None,
    printer_ip=None,
    printer_name=None,
    expected_status=None,
    strict_putaway=False,
):
    """Run legacy acceptance without its insecure HTTP thread, then queue safely."""
    if _ORIGINAL_ACCEPT_ITEM is None:
        raise RuntimeError('AcceptanceService hardening was not initialized.')

    result = _ORIGINAL_ACCEPT_ITEM(
        dostawa_id,
        item_id,
        lokalizacja,
        login,
        nr_partii,
        data_produkcji,
        data_przydatnosci,
        None,
        None,
        expected_status=expected_status,
        strict_putaway=strict_putaway,
    )
    try:
        success = bool(result and result[0])
        details = result[2] if success and len(result) > 2 else None
        if success and (printer_ip or printer_name):
            _queue_accepted_pallet_label(details, printer_ip, printer_name)
    except Exception:
        # Printing is ancillary; an already committed warehouse acceptance must
        # not be rolled back because a configured printer became unavailable.
        pass
    return result


def secure_admin_zpl_test():
    """Disable the legacy arbitrary-IP raw socket printer diagnostic."""
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
    """Install secure print replacements and refuse insecure partial startup."""
    replacements = {
        'magazyn_dostawy.dodruk_etykiet': secure_reprint_labels,
        'admin.admin_zpl_test': secure_admin_zpl_test,
        'admin.admin_printer_server_status': secure_admin_printer_server_status,
    }

    # Factory calls this after all blueprints are registered. If any legacy
    # endpoint disappeared from the expected registration order, continuing
    # could expose the original unauthenticated/raw-socket implementation.
    missing_endpoints = [
        endpoint for endpoint in replacements
        if endpoint not in app.view_functions
    ]
    if missing_endpoints:
        raise RuntimeError(
            'Legacy print hardening could not be installed; missing endpoints: '
            + ', '.join(sorted(missing_endpoints))
        )

    for endpoint, replacement in replacements.items():
        app.view_functions[endpoint] = replacement

    try:
        from app.blueprints.auth import base as auth_base
        auth_base._request_bridge = _secure_legacy_bridge_request
    except Exception as exc:
        raise RuntimeError(
            'Could not install authenticated legacy printer bridge helper.'
        ) from exc

    # Prevent one OS thread per newly created pallet. The legacy service only
    # uses threading.Thread for label dispatch, so a bounded executor adapter is
    # behavior-compatible while applying backpressure.
    try:
        from app.services.pallets import pallet_creation_service
        pallet_creation_service.threading = _BOUNDED_THREADING
    except Exception as exc:
        raise RuntimeError(
            'Could not install bounded pallet creation print workers.'
        ) from exc

    # AcceptanceService historically opened an unauthenticated localhost HTTP
    # request with verify=False in a new thread. Preserve its warehouse logic,
    # suppress that legacy print block, then queue the label through PrintServer.
    global _ORIGINAL_ACCEPT_ITEM
    try:
        from app.services.magazyn_dostawy.acceptance_service import AcceptanceService
        if _ORIGINAL_ACCEPT_ITEM is None:
            _ORIGINAL_ACCEPT_ITEM = AcceptanceService.accept_item
        AcceptanceService.accept_item = staticmethod(secure_accept_item)
    except Exception as exc:
        raise RuntimeError(
            'Could not install secure acceptance label printing.'
        ) from exc

    # Verify the security-sensitive replacements actually became active. This
    # catches future refactors that silently change endpoint names or imports.
    for endpoint, replacement in replacements.items():
        if app.view_functions.get(endpoint) is not replacement:
            raise RuntimeError(f'Legacy print endpoint was not hardened: {endpoint}')

    from app.services.magazyn_dostawy.acceptance_service import AcceptanceService
    if AcceptanceService.accept_item is not secure_accept_item:
        raise RuntimeError('AcceptanceService remained on the insecure legacy print path.')
