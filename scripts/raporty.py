"""Backward-compatible facade for report generation (Excel, PDF, text utils)."""
from pathlib import Path
from scripts.reports.text_utils import format_godziny, fix_mojibake, polskie_znaki_pdf
from scripts.reports.excel_report_exporter import ExcelReportExporter
from scripts.reports.pdf_report_generator import PdfReportGenerator

base_dir = Path(__file__).resolve().parent.parent
RAPORTY_PATH = str(base_dir / 'raporty')
try:
    Path(RAPORTY_PATH).mkdir(parents=True, exist_ok=True)
except PermissionError:
    pass


def generuj_excel(dzisiaj, prod_rows, awarie_rows, hr_rows):
    """Generates Excel report and returns file name."""
    return ExcelReportExporter.generuj_excel(dzisiaj, prod_rows, awarie_rows, hr_rows)


def generuj_pdf(
    dzisiaj, uwagi, lider, prod_rows, awarie_rows, hr_rows,
    folder, linia='PSD', obsada_rows=None, nieobecni_rows=None,
    bufor_rows=None, nadgodziny_rows=None, palety_rows=None
):
    """Generates PDF report and returns file name."""
    return PdfReportGenerator.generuj_pdf(
        dzisiaj=dzisiaj,
        uwagi=uwagi,
        lider=lider,
        prod_rows=prod_rows,
        awarie_rows=awarie_rows,
        hr_rows=hr_rows,
        folder=folder,
        linia=linia,
        obsada_rows=obsada_rows,
        nieobecni_rows=nieobecni_rows,
        bufor_rows=bufor_rows,
        nadgodziny_rows=nadgodziny_rows,
        palety_rows=palety_rows
    )