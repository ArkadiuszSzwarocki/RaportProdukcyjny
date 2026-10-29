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
        bufor_rows=None, nadgodziny_rows=None, palety_rows=None, measurements=None, order_times=None, opening_buffer=None, daily_progress=None
    ) -> str | None:
        linia_prefix = f"_{linia}" if linia else ""
        nazwa_pdf = f"Raport{linia_prefix}_{dzisiaj}.pdf"
        sciezka = os.path.join(RAPORTY_PATH, nazwa_pdf)
        print(f"[RAPORTY.generuj_pdf] START: dzisiaj={dzisiaj}, linia={linia}, sciezka={sciezka}")

        from fpdf import FPDF
        pdf = FPDF()
        from app.services.report_pdf_version import REPORT_LAYOUT_ID
        pdf.set_subject(REPORT_LAYOUT_ID)
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
        pdf.cell(0, 6, txt=polskie_znaki_pdf(f"Data zmiany: {dzisiaj} | Hala: {linia}"), ln=1)
        pdf.cell(0, 6, txt=polskie_znaki_pdf(f"Lider Zmiany: {lider_clean}"), ln=1)
        pdf.ln(1)

        # Notes

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
            if str(linia).upper() == 'AGRO' and sec in ('Workowanie', 'Czyszczenie'):
                prod_map[key]['_zasyp_excel_kg'] = r[8] if len(r) > 8 else None
                prod_map[key]['_settlement'] = r[9] if len(r)>9 else None

        # Production, Pallets, Downtime
        from scripts.reports.pdf_table_renderer import rysuj_wiersz_multicell,format_kg
        for section in ('Zasyp','Workowanie'):
            if section=='Workowanie':
                pdf.add_page()
                pdf.set_font('Arial','B',14)
                pdf.cell(0,10,polskie_znaki_pdf(f'WORKOWANIE - {dzisiaj} | {linia}'),ln=1)
            PdfProductionSections.render_production(pdf,products,prod_map,dzisiaj,awarie_rows,section=section)
            rows=[item for item in daily_progress or [] if item['section']==section]
            if rows:
                dates=sorted({day for item in rows for day in item['daily']})
                for offset in range(0,max(1,len(dates)),4):
                    selected=dates[offset:offset+4]
                    # Reserve the complete table before drawing its heading and rows.
                    estimated_height=24+len(rows)*16
                    if pdf.get_y()+estimated_height>270:pdf.add_page()
                    pdf.set_font('Arial','B',10)
                    pdf.cell(0,8,polskie_znaki_pdf(section+' - WYKONANIE DZIEN PO DNIU (kg)'),ln=1)
                    widths=[62,25]+[78/max(1,len(selected))]*len(selected)+[25]
                    header=['Zlecenie / produkt','Plan']+['Wyk. '+day[8:10]+'.'+day[5:7]+'.'+day[:4] for day in selected]+['Suma do '+str(dzisiaj)]
                    pdf.set_font('Arial',size=8)
                    rysuj_wiersz_multicell(pdf,widths,header,fill=True,font_style='B')
                    for item in rows:
                        values=[f"#{item['id']} {item['product']}",format_kg(item['plan']) if item['plan'] is not None else 'brak zasypu']+[format_kg(item['daily'][day]) if day in item['daily'] else '-' for day in selected]+[format_kg(item['total'])]
                        rysuj_wiersz_multicell(pdf,widths,values)
                    pdf.ln(4)
            times=[item for item in order_times or [] if item['section']==section]
            if times:
                pdf.set_text_color(30,41,59)
                pdf.set_font('Arial','B',10)
                pdf.cell(0,8,polskie_znaki_pdf('CZASY ZLECEN - '+section),ln=1)
                pdf.set_font('Arial',size=8)
                for item in times:
                    if pdf.get_y()+32>pdf.h-pdf.b_margin:pdf.add_page()
                    pdf.ln(2)
                    pdf.set_draw_color(203,213,225)
                    pdf.line(pdf.l_margin,pdf.get_y(),pdf.w-pdf.r_margin,pdf.get_y())
                    pdf.ln(2)
                    pdf.multi_cell(0,4,polskie_znaki_pdf(f"#{item['id']} {item['product']}\nStart: {item['start']} | Stop: {item['stop']}\nZapisany czas pracy: {item['saved']}\nCzas kalendarzowy START-STOP (z pauzami): {item.get('elapsed','brak danych')}\nOstatnie wznowienie: {item['resumed']}"))
        pdf.add_page()
        pdf.set_text_color(15,23,42)
        pdf.set_font('Arial','B',14)
        pdf.cell(0,10,polskie_znaki_pdf(f'NOTATKI, USTERKI I POSTOJE - {dzisiaj} | {linia}'),ln=1)
        if uwagi and str(uwagi).strip():
            PdfStaffSections.render_notes(pdf,uwagi)
        else:
            pdf.set_font('Arial',size=10)
            pdf.multi_cell(0,7,polskie_znaki_pdf('Brak zapisanych notatek zmianowych dla tego dnia.'))
        if awarie_rows:
            PdfProductionSections.render_downtime(pdf,awarie_rows)
        else:
            pdf.set_font('Arial',size=10)
            pdf.multi_cell(0,7,polskie_znaki_pdf('Brak zarejestrowanych usterek i postojow produkcyjnych dla tego dnia i hali.'))
        pdf.add_page()
        if opening_buffer:
            pdf.set_font('Arial','B',10)
            pdf.cell(0,8,polskie_znaki_pdf('BUFOR WEJSCIOWY - NIESPAKOWANE Z POPRZEDNICH DNI'),ln=1)
            pdf.set_font('Arial',size=9)
            for item in opening_buffer:
                pdf.multi_cell(0,6,polskie_znaki_pdf(f"#{item['id']} {item['product']}: {item['remaining']:.3f} kg"))
            pdf.multi_cell(0,5,polskie_znaki_pdf(f"Razem: {sum(item['remaining'] for item in opening_buffer):.3f} kg. Stan przed {dzisiaj} 00:00, dla zlecen raportu: zarejestrowany zasyp minus palety wczesniej wyprodukowane. Bilans ewidencyjny, bez szacowania brakujacych zapisow."))
        PdfProductionSections.render_pallets(pdf, palety_rows)
        if str(linia).upper() == 'AGRO':
            from scripts.reports.measurement_sections import render_pdf
            render_pdf(pdf, measurements)

        # Staff, HR, Absences, Overtime
        PdfStaffSections.render_obsada(pdf, obsada_rows, linia)
        PdfStaffSections.render_hr(pdf, hr_rows)
        PdfStaffSections.render_absences_and_kpi(pdf, nieobecni_rows, hr_rows)
        PdfStaffSections.render_overtime(pdf, nadgodziny_rows)

        actual_pdf_name = nazwa_pdf
        try:
            if os.path.exists(sciezka):
                try:
                    os.remove(sciezka)
                except Exception:
                    # Target is locked (e.g. open in iframe/browser on Windows)
                    sciezka = sciezka.replace('.pdf', '_new.pdf')
                    actual_pdf_name = nazwa_pdf.replace('.pdf', '_new.pdf')
        except Exception:
            pass

        try:
            pdf.output(sciezka)
            print(f"[RAPORTY] PDF saved to: {sciezka}")
            return actual_pdf_name
        except Exception as e:
            print(f"[RAPORTY] ERROR saving PDF to {sciezka}: {e}")
            try:
                # Secondary fallback with unique PID to guarantee successful write even if _new is locked
                fallback_name = f"Raport{linia_prefix}_{dzisiaj}_{os.getpid()}.pdf"
                fallback_path = os.path.join(RAPORTY_PATH, fallback_name)
                pdf.output(fallback_path)
                print(f"[RAPORTY] PDF fallback saved to: {fallback_path}")
                return fallback_name
            except Exception as e2:
                print(f"[RAPORTY] Fatal PDF write failure: {e2}")
                import traceback
                traceback.print_exc()
                return None
