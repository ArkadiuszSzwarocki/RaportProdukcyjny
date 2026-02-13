from pathlib import Path
from datetime import datetime
import zipfile
import os

def generuj_paczke_raportow(data_planu: str):
    """Generuje prosty testowy raport tekstowy dla podanej daty i zwraca listę ścieżek plików."""
    raporty_dir = Path("raporty")
    raporty_dir.mkdir(parents=True, exist_ok=True)
    safe_date = data_planu.replace(':', '-')
    filename = raporty_dir / f"test_report_{safe_date}.txt"
    content = (
        f"Testowy raport dla daty {data_planu}\n"
        f"Wygenerowano: {datetime.utcnow().isoformat()}Z\n"
        "To jest stub generujący przykładowe pliki raportów dla testów.\n"
    )
    filename.write_text(content, encoding="utf-8")
    return [str(filename)]

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
    return generuj_zip_z_raportow(files)
