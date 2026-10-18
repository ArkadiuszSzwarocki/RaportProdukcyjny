"""Require a real PDF in manually sent production reports."""
from pathlib import Path


def ensure_manual_pdf(attachments, day, line, notes, leader):
    paths = list(dict.fromkeys(str(path) for path in attachments))
    expected = f'Raport_{line}_{day}'
    pdf_paths = [Path(path) for path in paths if Path(path).suffix.lower() == '.pdf'
            and Path(path).stem in (expected, expected + '_new')]
    if not pdf_paths:
        from app.services.shift_close_service import _generate_report_files
        _, _, generated = _generate_report_files(day, notes, leader, linia=line)
        if generated:
            pdf_paths = [Path(generated)]
            paths.append(str(generated))
    if not pdf_paths:
        raise ValueError('Nie udało się wygenerować PDF. Raport nie został wysłany.')
    for path in pdf_paths:
        try:
            with path.open('rb') as handle:
                if handle.read(5) != b'%PDF-':
                    raise ValueError('Nieprawidłowy PDF. Raport nie został wysłany.')
        except OSError as exc:
            raise ValueError('Brak pliku PDF. Raport nie został wysłany.') from exc
    return paths
