"""PDF staff, attendance, overtime and notes rendering sections."""
from __future__ import annotations

from collections import defaultdict
from scripts.reports.text_utils import polskie_znaki_pdf
from scripts.reports.pdf_table_renderer import rysuj_wiersz_multicell


class PdfStaffSections:
    """Renders shift leader notes, station staff allocation, HR presence, absences and overtime."""

    @staticmethod
    def render_notes(pdf, uwagi):
        czyste_uwagi = (uwagi or "").replace("NOTATKI ZMIANOWE:\n", "").replace("-" * 50 + "\n", "").lstrip('|').strip()
        if czyste_uwagi and czyste_uwagi.lower() != "brak uwag i notatek lidera.":
            pdf.set_font("Arial", 'B', 10)
            pdf.set_fill_color(226, 232, 240)
            pdf.set_text_color(15, 23, 42)
            pdf.cell(0, 6, txt=polskie_znaki_pdf("NOTATKI I UWAGI ZMIANOWE:"), ln=1, fill=True)
            pdf.set_text_color(30, 41, 59)
            pdf.set_font("Arial", size=9)
            pdf.set_fill_color(248, 250, 252)
            pdf.multi_cell(0, 6, txt=polskie_znaki_pdf(czyste_uwagi), border=1, fill=True)
            pdf.ln(4)

    @staticmethod
    def render_obsada(pdf, obsada_rows, linia):
        obsada_rows = obsada_rows or []
        sekcje_obsady = defaultdict(list)
        total_assigned_staff = 0
        for r in obsada_rows:
            sec = (r[0] if len(r) > 0 and r[0] else 'Inne').strip()
            osoba = (r[1] if len(r) > 1 and r[1] else '').strip()
            funkcja = f" ({r[2]})" if len(r) > 2 and r[2] else ""
            if osoba:
                sekcje_obsady[sec].append(f"{osoba}{funkcja}")
                total_assigned_staff += 1

        if any(len(osoby) > 0 for osoby in sekcje_obsady.values()):
            pdf.set_font("Arial", 'B', 11)
            pdf.set_fill_color(30, 41, 59)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(0, 7, polskie_znaki_pdf(f"OBSADA STANOWISKOWA — LINIA {linia.upper()} (PRZYDZIAŁ DO STANOWISK: {total_assigned_staff} OS.)"), ln=1, fill=True)
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Arial", size=9)

            for sec, osoby in sekcje_obsady.items():
                if not osoby:
                    continue
                pdf.set_font("Arial", 'B', 9)
                pdf.set_fill_color(226, 232, 240)
                pdf.cell(0, 6, polskie_znaki_pdf(f" Stanowisko: {sec} ({len(osoby)} os.)"), 1, 1, 'L', True)
                pdf.set_font("Arial", size=9)
                for idx, osoba in enumerate(osoby, 1):
                    row_color = (255, 255, 255) if idx % 2 != 0 else (248, 250, 252)
                    pdf.set_fill_color(*row_color)
                    pdf.cell(0, 6, polskie_znaki_pdf(f"     {idx}. {osoba}"), 1, 1, 'L', True)
            pdf.ln(4)

    @staticmethod
    def render_hr(pdf, hr_rows):
        hr_rows = hr_rows or []
        if hr_rows:
            pdf.set_font("Arial", 'B', 11)
            pdf.set_fill_color(37, 99, 235)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(0, 7, polskie_znaki_pdf(f"OBECNOŚĆ NA ZMIANIE — PRACOWNICY OBECNI ({len(hr_rows)} OS.)"), ln=1, fill=True)
            pdf.set_text_color(0, 0, 0)

            col_hr = (12, 75, 55, 25, 23)
            rysuj_wiersz_multicell(pdf, col_hr, ["Lp.", "Pracownik", "Stanowisko / Sekcja", "Status", "Czas pracy"], col_aligns=['C', 'L', 'L', 'C', 'C'], fill=True, fill_color=(235, 243, 255), font_style='B')

            pdf.set_font("Arial", size=9)
            fill = False
            total_hr_hours = 0.0
            for idx, r in enumerate(hr_rows, 1):
                prac = str(r[0] if len(r) > 0 and r[0] else '')
                sec = str(r[1] if len(r) > 1 and r[1] else 'Brak przydziału')
                typ_st = str(r[2] if len(r) > 2 and r[2] else 'Obecny')
                try:
                    g_val = float(r[3]) if len(r) > 3 and r[3] is not None else 8.0
                except Exception:
                    g_val = 8.0
                total_hr_hours += g_val
                godz_str = f"{g_val:.1f}h"
                row_color = (250, 250, 250) if fill else (255, 255, 255)
                rysuj_wiersz_multicell(pdf, col_hr, [str(idx), prac, sec, typ_st, godz_str], col_aligns=['C', 'L', 'L', 'C', 'C'], fill=fill, fill_color=row_color, font_style='')
                fill = not fill

            pdf.set_font("Arial", 'B', 9)
            pdf.set_fill_color(240, 245, 255)
            pdf.cell(167, 7, polskie_znaki_pdf(f"ŁĄCZNIE OBECNYCH NA ZMIANIE ({len(hr_rows)} OSÓB):"), 1, 0, 'R', True)
            pdf.cell(23, 7, f"{total_hr_hours:.1f}h", 1, 1, 'C', True)
            pdf.ln(4)

    @staticmethod
    def render_absences_and_kpi(pdf, nieobecni_rows, hr_rows):
        nieobecni_rows = nieobecni_rows or []
        if nieobecni_rows:
            pdf.set_font("Arial", 'B', 11)
            pdf.set_fill_color(142, 68, 173)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(0, 7, polskie_znaki_pdf(f"NIEOBECNOŚCI, URLOPY I WYJŚCIA PRYWATNE ({len(nieobecni_rows)} OS.)"), ln=1, fill=True)
            pdf.set_text_color(0, 0, 0)

            col_nieob = (12, 68, 50, 60)
            rysuj_wiersz_multicell(pdf, col_nieob, ["Lp.", "Pracownik", "Typ", "Powód / Godziny / Komentarz"], col_aligns=['C', 'L', 'C', 'L'], fill=True, fill_color=(245, 235, 250), font_style='B')

            pdf.set_font("Arial", size=9)
            fill = False
            for idx, r in enumerate(nieobecni_rows, 1):
                prac = str(r[0] if len(r) > 0 and r[0] else '')
                typ_nieob = str(r[1] if len(r) > 1 and r[1] else 'Nieobecność').upper()
                kom = str(r[2] if len(r) > 2 and r[2] else '-')
                row_color = (250, 250, 250) if fill else (255, 255, 255)
                rysuj_wiersz_multicell(pdf, col_nieob, [str(idx), prac, typ_nieob, kom], col_aligns=['C', 'L', 'C', 'L'], fill=fill, fill_color=row_color, font_style='')
                fill = not fill

            pdf.set_font("Arial", 'B', 9)
            pdf.set_fill_color(250, 240, 255)
            pdf.cell(0, 7, polskie_znaki_pdf(f"ŁĄCZNIE NIEOBECNYCH / NA URLOPIE / WYJŚCIA: {len(nieobecni_rows)} OSÓB"), 1, 1, 'L', True)
            pdf.ln(4)

        cnt_obecni = len(hr_rows) if hr_rows else 0
        cnt_nieobecni = len(nieobecni_rows) if nieobecni_rows else 0
        cnt_total = cnt_obecni + cnt_nieobecni
        if cnt_total > 0:
            frekwencja_pct = round((cnt_obecni / cnt_total) * 100, 1)
            pdf.set_font("Arial", 'B', 9)
            pdf.set_fill_color(241, 245, 249)
            pdf.set_text_color(30, 41, 59)
            info_frekwencja = f"PODSUMOWANIE OBSADY I FREKWENCJI:  Obecni: {cnt_obecni} os.  |  Urlop / L4 / Nieobecni: {cnt_nieobecni} os.  |  Łączny stan: {cnt_total} os.  |  Frekwencja: {frekwencja_pct}%"
            pdf.cell(0, 6, polskie_znaki_pdf(info_frekwencja), 1, 1, 'C', True)
            pdf.ln(4)

    @staticmethod
    def render_overtime(pdf, nadgodziny_rows):
        nadgodziny_rows = nadgodziny_rows or []
        if nadgodziny_rows:
            pdf.set_font("Arial", 'B', 11)
            pdf.set_fill_color(23, 32, 42)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(0, 7, polskie_znaki_pdf("NADGODZINY"), ln=1, fill=True)
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Arial", 'B', 9)
            pdf.set_fill_color(220, 220, 220)
            pdf.cell(70, 7, polskie_znaki_pdf("Pracownik"), 1, 0, 'L', True)
            pdf.cell(20, 7, polskie_znaki_pdf("Godz."), 1, 0, 'C', True)
            pdf.cell(30, 7, polskie_znaki_pdf("Status"), 1, 0, 'C', True)
            pdf.cell(70, 7, polskie_znaki_pdf("Powód"), 1, 1, 'L', True)
            pdf.set_font("Arial", size=9)
            fill = False
            for r in nadgodziny_rows:
                pdf.set_fill_color(245, 245, 245) if fill else pdf.set_fill_color(255, 255, 255)
                try:
                    godz = f"{float(r[1]):.1f}h"
                except Exception:
                    godz = str(r[1])
                pdf.cell(70, 7, polskie_znaki_pdf(str(r[0])), 1, 0, 'L', fill)
                pdf.cell(20, 7, godz, 1, 0, 'C', fill)
                pdf.cell(30, 7, polskie_znaki_pdf(str(r[3])), 1, 0, 'C', fill)
                pdf.cell(70, 7, polskie_znaki_pdf(str(r[2])[:45]), 1, 1, 'L', fill)
                fill = not fill
            pdf.ln(4)
