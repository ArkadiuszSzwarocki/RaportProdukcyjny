"""PDF report builder orchestrating page flow and layout."""
from __future__ import annotations

import os
from pathlib import Path
from scripts.reports.text_utils import polskie_znaki_pdf
from scripts.reports.pdf_production_sections import PdfProductionSections
from scripts.reports.pdf_staff_sections import PdfStaffSections

BASE_DIR = Path(__file__).resolve().parent.parent.parent
RAPORTY_PATH = str(BASE_DIR / 'raporty')
try:
    Path(RAPORTY_PATH).mkdir(parents=True, exist_ok=True)
except PermissionError:
    pass


class PdfReportGenerator:
    """Orchestrates comprehensive shift report generation into PDF."""

    @staticmethod
    def generuj_pdf(
        dzisiaj, uwagi, lider, prod_rows, awarie_rows, hr_rows,
        folder, linia='PSD', obsada_rows=None, nieobecni_rows=None,
        bufor_rows=None, nadgodziny_rows=None, palety_rows=None
    ) -> str | None:
        linia_prefix = f"_{linia}" if linia else ""
        nazwa_pdf = f"Raport{linia_prefix}_{dzisiaj}.pdf"
        sciezka = os.path.join(RAPORTY_PATH, nazwa_pdf)
        print(f"[RAPORTY.generuj_pdf] START: dzisiaj={dzisiaj}, linia={linia}, sciezka={sciezka}")

        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_draw_color(80, 80, 80)
        pdf.set_line_width(0.35)

        # Header
        pdf.set_font("Arial", 'B', 16)
        pdf.set_fill_color(41, 128, 185)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 12, txt=polskie_znaki_pdf(f"RAPORT ZMIANY: {dzisiaj}"), ln=1, align='C', fill=True)
        pdf.ln(3)

        # Shift Leader
        lider_clean = str(lider or '').lstrip('|').strip()
        pdf.set_text_color(30, 41, 59)
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(0, 6, txt=polskie_znaki_pdf(f"Lider Zmiany: {lider_clean}"), ln=1)
        pdf.ln(1)

        # Notes
        PdfStaffSections.render_notes(pdf, uwagi)

        # Map products
        products = []
        prod_map = {}
        for r in prod_rows:
            sec = r[0] if len(r) > 0 else ''
            prod = r[1] if len(r) > 1 else ''
            plan = r[2] if len(r) > 2 else None
            wyk = r[3] if len(r) > 3 else None
            r_start = r[4] if len(r) > 4 else None
            r_stop = r[5] if len(r) > 5 else None
            zlec = r[6] if len(r) > 6 else ''
            plan_id = r[7] if len(r) > 7 else ''
            if not zlec or not str(zlec).strip():
                zlec = f"ID: {plan_id}"

            key = ' '.join(str(prod).strip().split()) if prod is not None else ""
            if key not in prod_map:
                prod_map[key] = {'_display': prod}
                products.append(key)
            prod_map[key][sec] = (plan, wyk, r_start, r_stop, zlec)

        # Production, Pallets, Downtime
        PdfProductionSections.render_production(pdf, products, prod_map, dzisiaj, awarie_rows)
        PdfProductionSections.render_pallets(pdf, palety_rows)
        PdfProductionSections.render_downtime(pdf, awarie_rows)

        # Staff, HR, Absences, Overtime
        PdfStaffSections.render_obsada(pdf, obsada_rows, linia)
        PdfStaffSections.render_hr(pdf, hr_rows)
        PdfStaffSections.render_absences_and_kpi(pdf, nieobecni_rows, hr_rows)
        PdfStaffSections.render_overtime(pdf, nadgodziny_rows)

        try:
            if os.path.exists(sciezka):
                try:
                    os.remove(sciezka)
                except Exception:
                    sciezka = sciezka.replace('.pdf', '_new.pdf')
        except Exception:
            pass

        try:
            pdf.output(sciezka)
            print(f"[RAPORTY] PDF saved to: {sciezka}")
            return nazwa_pdf
        except Exception as e:
            print(f"[RAPORTY] ERROR saving PDF to {sciezka}: {e}")
            import traceback
            traceback.print_exc()
            return None
