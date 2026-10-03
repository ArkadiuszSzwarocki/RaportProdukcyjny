"""File upload and server-side attachment guards added by the security audit."""

import os
from functools import wraps
from pathlib import Path
from datetime import date

from flask import current_app, flash, jsonify, redirect, request, session, url_for


QUALITY_ALLOWED_EXTENSIONS = {
    '.pdf', '.png', '.jpg', '.jpeg', '.webp',
    '.xlsx', '.xls', '.csv', '.txt', '.docx',
}
BUG_ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
REPORT_ALLOWED_EXTENSIONS = {'.pdf', '.xlsx'}
QUALITY_MAX_BYTES = 10 * 1024 * 1024
BUG_MAX_BYTES = 4 * 1024 * 1024
BUG_MAX_FILES = 3


def _file_size(file_storage) -> int:
    """Return upload size without consuming the stream."""
    stream = getattr(file_storage, 'stream', None)
    if stream is None:
        return 0
    try:
        current = stream.tell()
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(current, os.SEEK_SET)
        return int(size)
    except Exception:
        return -1


def _prefix(file_storage, length=32) -> bytes:
    stream = getattr(file_storage, 'stream', None)
    if stream is None:
        return b''
    try:
        current = stream.tell()
        stream.seek(0)
        data = stream.read(length)
        stream.seek(current)
        return bytes(data or b'')
    except Exception:
        return b''


def _image_signature_valid(ext: str, prefix: bytes) -> bool:
    ext = ext.lower()
    if ext in {'.jpg', '.jpeg'}:
        return prefix.startswith(b'\xff\xd8\xff')
    if ext == '.png':
        return prefix.startswith(b'\x89PNG\r\n\x1a\n')
    if ext == '.gif':
        return prefix.startswith((b'GIF87a', b'GIF89a'))
    if ext == '.webp':
        return len(prefix) >= 12 and prefix[:4] == b'RIFF' and prefix[8:12] == b'WEBP'
    return True


def _quality_upload_valid(file_storage):
    filename = str(getattr(file_storage, 'filename', '') or '')
    ext = Path(filename).suffix.lower()
    if ext not in QUALITY_ALLOWED_EXTENSIONS:
        return False, 'Niedozwolony typ pliku. Dozwolone są dokumenty, arkusze, PDF i obrazy.'

    size = _file_size(file_storage)
    if size < 0 or size > QUALITY_MAX_BYTES:
        return False, 'Plik jest zbyt duży. Maksymalny rozmiar to 10 MB.'
    if size == 0:
        return False, 'Nie można przesłać pustego pliku.'

    prefix = _prefix(file_storage)
    if ext in {'.png', '.jpg', '.jpeg', '.webp'} and not _image_signature_valid(ext, prefix):
        return False, 'Zawartość pliku nie odpowiada jego rozszerzeniu.'
    if ext == '.pdf' and not prefix.startswith(b'%PDF-'):
        return False, 'Nieprawidłowy plik PDF.'
    if ext in {'.xlsx', '.docx'} and not prefix.startswith(b'PK'):
        return False, 'Nieprawidłowy dokument Office.'
    if ext == '.xls' and not prefix.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
        return False, 'Nieprawidłowy plik XLS.'
    if ext in {'.csv', '.txt'} and b'\x00' in prefix:
        return False, 'Plik tekstowy zawiera niedozwolone dane binarne.'
    return True, ''


def _bug_uploads_valid(files):
    actual = [item for item in files if item and getattr(item, 'filename', '')]
    if len(actual) > BUG_MAX_FILES:
        return False, 'Można dodać maksymalnie 3 zrzuty ekranu.'
    for file_storage in actual:
        ext = Path(file_storage.filename).suffix.lower()
        if ext not in BUG_ALLOWED_EXTENSIONS:
            return False, 'Załączniki zgłoszenia muszą być obrazami PNG/JPG/GIF/WEBP.'
        size = _file_size(file_storage)
        if size <= 0 or size > BUG_MAX_BYTES:
            return False, 'Każdy zrzut ekranu może mieć maksymalnie 4 MB.'
        if not _image_signature_valid(ext, _prefix(file_storage)):
            return False, 'Zawartość obrazu nie odpowiada jego rozszerzeniu.'
    return True, ''


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def report_attachment_path_allowed(raw_path) -> bool:
    """Allow only generated report files, never arbitrary server filesystem paths."""
    if not raw_path:
        return False
    try:
        candidate = Path(str(raw_path)).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    if not candidate.is_file() or candidate.suffix.lower() not in REPORT_ALLOWED_EXTENSIONS:
        return False

    try:
        from app.services.shift_close_service import RAPORTY_DIR, RAPORTY_TEMP_DIR
        roots = [Path(RAPORTY_DIR).resolve(), Path(RAPORTY_TEMP_DIR).resolve()]
    except Exception:
        return False
    return any(_is_within(candidate, root) for root in roots)


def _quality_upload_guard(original_view):
    @wraps(original_view)
    def guarded(*args, **kwargs):
        if request.method == 'POST':
            upload = request.files.get('file')
            if upload and upload.filename:
                allowed, message = _quality_upload_valid(upload)
                if not allowed:
                    flash(message, 'danger')
                    plan_id = kwargs.get('plan_id')
                    linia = request.form.get('linia') or request.args.get('linia') or 'PSD'
                    return redirect(url_for('quality.jakosc_detail', plan_id=plan_id, linia=linia))
        return original_view(*args, **kwargs)
    return guarded


def _bug_upload_guard(original_view):
    @wraps(original_view)
    def guarded(*args, **kwargs):
        allowed, message = _bug_uploads_valid(request.files.getlist('zalaczniki'))
        if not allowed:
            return jsonify({'success': False, 'message': message}), 400
        return original_view(*args, **kwargs)
    return guarded


def _report_attachment_guard(original_view):
    @wraps(original_view)
    def guarded(*args, **kwargs):
        submitted = request.form.getlist('attachments')
        line = str(request.form.get('linia') or request.args.get('linia') or
                   session.get('selected_hall_view') or 'PSD').strip().upper()
        day = request.form.get('date_str') or str(date.today())
        try:
            valid_day = date.fromisoformat(day).isoformat() == day
        except (ValueError, TypeError):
            valid_day = False
        if line not in {'PSD', 'AGRO', 'OSIP'} or not valid_day:
            return jsonify(success=False, message='Nieprawidłowa hala lub data raportu.'), 400
        expected_names = {f'Raport_{line}_{day}.pdf', f'Raport_{line}_{day}.xlsx'}
        invalid = [value for value in submitted if not report_attachment_path_allowed(value)
                   or Path(str(value)).name not in expected_names]
        if invalid:
            current_app.logger.warning(
                'Rejected untrusted report attachment path from user=%s count=%d',
                request.cookies.get('session') and 'authenticated' or 'unknown',
                len(invalid),
            )
            return jsonify({
                'success': False,
                'message': 'Wybrano niedozwolony załącznik raportu. Odśwież stronę i wybierz plik ponownie.',
            }), 400
        return original_view(*args, **kwargs)
    return guarded


def _wrap_once(app, endpoint, wrapper, marker):
    original = app.view_functions.get(endpoint)
    if original is None:
        raise RuntimeError(f'File security hardening missing endpoint: {endpoint}')
    if getattr(original, marker, False):
        return
    guarded = wrapper(original)
    setattr(guarded, marker, True)
    app.view_functions[endpoint] = guarded


def register_file_security_hardening(app) -> None:
    _wrap_once(app, 'quality.jakosc_detail', _quality_upload_guard, '_audit_quality_upload_guard')
    _wrap_once(app, 'main.zglos_blad_systemu', _bug_upload_guard, '_audit_bug_upload_guard')
    _wrap_once(
        app,
        'main.raport_zakoncz_zmiane_wyslij',
        _report_attachment_guard,
        '_audit_report_attachment_guard',
    )
