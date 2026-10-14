"""Download route guards added by the security audit."""

import os
import re
from functools import wraps

from flask import abort


_REPORT_FILENAME_RE = re.compile(
    r'^Raport_[A-Za-z0-9]+_\d{4}-\d{2}-\d{2}\.(?:pdf|xlsx)$',
    re.IGNORECASE,
)


def report_download_filename_allowed(filename) -> bool:
    """Return True only for generated production-report filenames."""
    raw = str(filename or '')
    if not raw:
        return False
    if raw != os.path.basename(raw):
        return False
    if '/' in raw or '\\' in raw or '\x00' in raw:
        return False
    return bool(_REPORT_FILENAME_RE.fullmatch(raw))


def _report_download_guard(original_view):
    @wraps(original_view)
    def guarded(filename, *args, **kwargs):
        if not report_download_filename_allowed(filename):
            abort(404)
        return original_view(filename, *args, **kwargs)
    return guarded


def register_download_security_hardening(app) -> None:
    endpoint = 'zarzad.pobierz_plik_raportu'
    original = app.view_functions.get(endpoint)
    if original is None:
        raise RuntimeError(f'Download security hardening missing endpoint: {endpoint}')
    if getattr(original, '_audit_report_download_guard', False):
        return

    guarded = _report_download_guard(original)
    guarded._audit_report_download_guard = True
    app.view_functions[endpoint] = guarded
