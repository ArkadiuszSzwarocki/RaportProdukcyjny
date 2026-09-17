"""Excel report generator for shift reports."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
RAPORTY_PATH = str(BASE_DIR / 'raporty')
try:
    Path(RAPORTY_PATH).mkdir(parents=True, exist_ok=True)
except PermissionError:
    pass


class ExcelReportExporter:
    """Exports production, maintenance and HR rows into an Excel file."""

    @staticmethod
    def generuj_excel(dzisiaj, prod_rows, awarie_rows, hr_rows) -> str:
        nazwa_excel = f"Raport_{dzisiaj}.xlsx"
        sciezka = os.path.join(RAPORTY_PATH, nazwa_excel)
        import pandas as pd

        with pd.ExcelWriter(sciezka, engine='openpyxl') as writer:
            pd.DataFrame(prod_rows, columns=['Sekcja', 'Produkt', 'Plan', 'Wykonanie']).to_excel(writer, sheet_name='Produkcja', index=False)
            pd.DataFrame(awarie_rows, columns=['Sekcja', 'Kategoria', 'Problem', 'Start', 'Stop', 'Minuty']).to_excel(writer, sheet_name='Awarie', index=False)
            pd.DataFrame(hr_rows, columns=['Pracownik', 'Typ', 'Godziny']).to_excel(writer, sheet_name='HR', index=False)

        return nazwa_excel
