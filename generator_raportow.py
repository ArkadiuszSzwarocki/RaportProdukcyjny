"""
Compatibility wrapper for report generator.

The project contains a richer implementation at `scripts/generator_raportow.py`
that expects signature `generuj_paczke_raportow(data, uwagi, lider_name='')`.
Some parts of the app import `generator_raportow` from the project root; the
root-level module previously exposed a different signature which caused a
TypeError when the app called it with three arguments. To remain backward
compatible, delegate to `scripts.generator_raportow` when available and
otherwise provide a minimal fallback that accepts the extended signature.
"""

from pathlib import Path
from datetime import datetime
import zipfile
import logging

logger = logging.getLogger(__name__)

_delegate = None
try:
    # Prefer the full-featured implementation if present
    from scripts.generator_raportow import generuj_paczke_raportow as _delegate
except Exception:
    _delegate = None


def generuj_paczke_raportow(data_planu, uwagi_lidera='', lider_name=''):
    """Generate report package.

    If `scripts.generator_raportow` is available, call it with the full
    arguments. Otherwise create a simple text report file (fallback).
    Returns either (xls_path, txt_path, pdf_path) or a list of file paths
    depending on the delegate implementation; callers in the app expect
    either variant — higher-level callers use `generuj_excel_zmiany` which
    handles both.
    """
    if _delegate:
        # delegate is expected to return (xls, txt, pdf) or similar
        return _delegate(data_planu, uwagi_lidera, lider_name)

    # fallback simple implementation (keeps old behaviour but accepts extra args)
    raporty_dir = Path("raporty")
    raporty_dir.mkdir(parents=True, exist_ok=True)
    safe_date = str(data_planu).replace(':', '-')
    txt_path = raporty_dir / f"test_report_{safe_date}.txt"
    content = (
        f"Testowy raport dla daty {data_planu}\n"
        f"Uwagi: {uwagi_lidera}\n"
        f"Lider: {lider_name}\n"
        f"Wygenerowano: {datetime.utcnow().isoformat()}Z\n"
        "To jest fallback stub generujący przykładowe pliki raportów dla testów.\n"
    )
    txt_path.write_text(content, encoding="utf-8")
    return [str(txt_path)]


def generuj_zip_z_raportow(file_paths):
    """Pakuje podane pliki do ZIP-a i zwraca ścieżkę do archiwum."""
    raporty_dir = Path("raporty")
    raporty_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    zip_path = raporty_dir / f"test_reports_{timestamp}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in file_paths:
            ppath = Path(p)
            if ppath.exists():
                zf.write(ppath, arcname=ppath.name)
    return str(zip_path)


def generuj_i_pakuj(data_planu: str):
    """Wygeneruj raporty i zwróć ścieżkę do wygenerowanego ZIP-a."""
    files = generuj_paczke_raportow(data_planu)
    # If delegate already returns zipped path, allow that
    if isinstance(files, str) and files.endswith('.zip'):
        return files
    return generuj_zip_z_raportow(files)
