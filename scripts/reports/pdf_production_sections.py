"""PDF sections rendering: Production tables, pallet summary and downtime."""
from __future__ import annotations

import math
from scripts.reports.text_utils import polskie_znaki_pdf
from scripts.reports.pdf_table_renderer import rysuj_wiersz_multicell, format_kg


class PdfProductionSections:
    """Renders production batches, productivity and downtime tables."""

    @staticmethod
    def render_production(pdf, products, prod_map, dzisiaj, awarie_rows):
        def _rysuj_tabele_sekcji(tytul, sekcje_klucze):
            has_data = False
            for prod in products:
                for s_klucz in sekcje_klucze:
                    if s_klucz in prod_map.get(prod, {}):
                        has_data = True
                        break

            if not has_data:
                return

            pdf.set_font("Arial", 'B', 12)
            pdf.set_fill_color(52, 73, 94)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(0, 8, polskie_znaki_pdf(f"PRODUKCJA - {tytul}"), ln=1, fill=True)
            
            pdf.set_text_color(0, 0, 0)
            pdf.set_fill_color(240, 240, 240)
            pdf.set_font("Arial", 'B', 9)
            col_w = (42, 58, 22, 22, 23, 23)
            
            rysuj_wiersz_multicell(
                pdf, col_w, ["Zlecenie", "Produkt", "Plan", "Wykonanie", "Start", "Stop"],
                col_aligns=['C', 'C', 'C', 'C', 'C', 'C'], fill=True, fill_color=(240, 240, 240), font_style='B'
            )

            pdf.set_font("Arial", size=9)
            fill = False
            for prod in products:
                p_data = None
                for s_klucz in sekcje_klucze:
                    if s_klucz in prod_map.get(prod, {}):
                        p_data = prod_map[prod][s_klucz]
                        break
                if not p_data:
                    continue

                plan, wyk, r_start, r_stop, zlec_raw = p_data
                zlec = str(zlec_raw) if zlec_raw else "Brak"
                prod_name = str(prod_map[prod].get('_display', prod))

                try:
                    pval = float(plan) if plan is not None else 0.0
                except Exception:
                    pval = 0.0
                try:
                    wval = float(wyk) if wyk is not None else 0.0
                except Exception:
                    wval = 0.0

                if tytul == 'WORKOWANIE':
                    try:
                        z_wyk_raw = prod_map.get(prod, {}).get('Zasyp', (None, None))[1]
                        if z_wyk_raw is not None:
                            z_val = float(z_wyk_raw)
                            if not math.isnan(z_val) and z_val > 0:
                                pval = z_val
                    except Exception:
                        pass

                plan_str = format_kg(pval) if pval else "-"
                wyk_str = format_kg(wval) if (wval or wval == 0) else "-"

                s_str, e_str = "-", "-"
                if r_start and str(r_start) not in ('NaT', 'None', 'nan', ''):
                    try:
                        s_str = r_start.strftime('%H:%M')
                    except Exception:
                        s_str = str(r_start)[:5] if str(r_start) != 'NaT' else "-"
                if r_stop and str(r_stop) not in ('NaT', 'None', 'nan', ''):
                    try:
                        e_str = r_stop.strftime('%H:%M')
                    except Exception:
                        e_str = str(r_stop)[:5] if str(r_stop) != 'NaT' else "-"

                row_color = (250, 250, 250) if fill else (255, 255, 255)
                rysuj_wiersz_multicell(
                    pdf, col_w, [zlec, prod_name, plan_str, wyk_str, s_str, e_str],
                    col_aligns=['L', 'L', 'C', 'C', 'C', 'C'], fill=fill, fill_color=row_color, font_style=''
                )
                fill = not fill

                if tytul == 'WORKOWANIE':
                    try:
                        z_wyk_raw = prod_map.get(prod, {}).get('Zasyp', (None, None))[1]
                        z_plan = float(z_wyk_raw) if z_wyk_raw is not None else 0.0
                        if math.isnan(z_plan):
                            z_plan = 0.0
                    except Exception:
                        z_plan = 0.0
                    diff = wval - z_plan
                    diff_sign = '+' if diff >= 0 else '-'
                    diff_abs = abs(diff)
                    if math.isclose(diff_abs, round(diff_abs), abs_tol=1e-9):
                        diff_str = f"{diff_sign}{int(round(diff_abs))} kg"
                    else:
                        diff_str = f"{diff_sign}{round(diff_abs,1):.1f} kg"
                    
                    pdf.set_font("Arial", 'B', 8)
                    if diff >= 0:
                        pdf.set_text_color(34, 139, 34)
                    else:
                        pdf.set_text_color(192, 57, 43)
                    pdf.cell(190, 5, polskie_znaki_pdf(f"Rozliczenie względem zasypu: {diff_str}"), 1, 1, 'R', True)
                    pdf.set_text_color(0, 0, 0)
                    pdf.set_font("Arial", size=9)

            if tytul == 'ZASYP' and has_data:
                suma_wyk_zasyp = 0.0
                for prod in products:
                    if 'Zasyp' in prod_map.get(prod, {}):
                        w_val = prod_map[prod]['Zasyp'][1]
                        try:
                            if w_val is not None:
                                val = float(w_val)
                                if not math.isnan(val):
                                    suma_wyk_zasyp += val
                        except Exception:
                            pass
                
                awarie_zasyp_min = 0
                if awarie_rows:
                    for r in awarie_rows:
                        sek = str(r[0] if len(r) > 0 and r[0] else '').strip().lower()
                        if 'zasyp' in sek:
                            try:
                                awarie_zasyp_min += int(r[5] or 0)
                            except Exception:
                                pass
                
                from app.services.shift_time_service import ShiftTimeService
                prod_metrics = ShiftTimeService.calculate_productivity(
                    mass_kg=suma_wyk_zasyp,
                    awarie_min=awarie_zasyp_min,
                    date_str=str(dzisiaj)
                )
                
                pdf.set_font("Arial", 'B', 9)
                pdf.set_fill_color(225, 245, 235)
                pdf.set_text_color(15, 80, 45)
                info_txt1 = f"Wydajność efektywna (netto): {prod_metrics['wydajnosc_efektywna']:.1f} kg/h (wykonane w {prod_metrics['netto_min']} min produkcyjnych [{prod_metrics['brutto_min']} min - {awarie_zasyp_min} min awarie])"
                pdf.cell(190, 6, polskie_znaki_pdf(info_txt1), 1, 1, 'L', True)
                
                pdf.set_fill_color(238, 246, 255)
                pdf.set_text_color(20, 70, 140)
                info_txt2 = f"Wydajność rzeczywista (brutto / {prod_metrics['start_str']}–{prod_metrics['end_str']}): {prod_metrics['wydajnosc_rzeczywista']:.1f} kg/h ({format_kg(suma_wyk_zasyp)} / {prod_metrics['brutto_min']} min * 60)"
                pdf.cell(190, 6, polskie_znaki_pdf(info_txt2), 1, 1, 'L', True)
                pdf.set_text_color(0, 0, 0)
                pdf.set_font("Arial", size=9)

            pdf.ln(5)

        has_zasyp = any('Zasyp' in prod_map.get(prod, {}) for prod in products)
        has_work = any(('Workowanie' in prod_map.get(prod, {}) or 'Czyszczenie' in prod_map.get(prod, {})) for prod in products)

        if not has_zasyp and not has_work:
            pdf.set_font("Arial", 'B', 11)
            pdf.set_fill_color(241, 245, 249)
            pdf.set_text_color(51, 65, 85)
            pdf.cell(0, 7, polskie_znaki_pdf("REALIZACJA PRODUKCJI"), ln=1, fill=True)
            pdf.set_font("Arial", 'B', 9)
            pdf.set_fill_color(254, 242, 242)
            pdf.set_text_color(185, 28, 28)
            pdf.cell(0, 8, polskie_znaki_pdf("W DANYM DNIU NIE REJESTROWANO PRODUKCJI (BRAK ZAPLANOWANYCH / WYKONANYCH ZLECEŃ)"), 1, 1, 'C', True)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(4)
        else:
            if has_zasyp:
                _rysuj_tabele_sekcji('ZASYP', ['Zasyp'])
            if has_work:
                _rysuj_tabele_sekcji('WORKOWANIE', ['Workowanie', 'Czyszczenie'])

    @staticmethod
    def render_pallets(pdf, palety_rows):
        if not palety_rows:
            return
        pdf.set_font("Arial", 'B', 12)
        pdf.set_fill_color(243, 156, 18)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 8, polskie_znaki_pdf("WYPRODUKOWANE PALETY (W DNIU RAPORTU)"), ln=1, fill=True)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", size=9)
        pdf.ln(2)

        col_pal = (55, 60, 30, 20, 25)
        rysuj_wiersz_multicell(pdf, col_pal, ["Zlecenie", "Produkt", "Opakowanie", "Sztuk", "Waga"], col_aligns=['C', 'C', 'C', 'C', 'C'], fill=True, fill_color=(230, 230, 230), font_style='B')
        fill = False
        pdf.set_font("Arial", size=9)
        total_szt, total_wg = 0, 0.0
        for r in palety_rows:
            zlec = str(r[0]) if r[0] else "Brak"
            prod = str(r[1]) if r[1] else "Brak"
            szt = int(r[2]) if r[2] else 0
            wg = float(r[3]) if r[3] else 0.0
            opak = str(r[4]).capitalize() if len(r) > 4 and r[4] else "Worki"
            total_szt += szt
            total_wg += wg
            row_color = (250, 250, 250) if fill else (255, 255, 255)
            rysuj_wiersz_multicell(pdf, col_pal, [zlec, prod, opak, f"{szt} szt.", format_kg(wg)], col_aligns=['L', 'L', 'C', 'C', 'C'], fill=fill, fill_color=row_color, font_style='')
            fill = not fill
            
        pdf.set_font("Arial", 'B', 9)
        pdf.set_fill_color(250, 235, 215)
        pdf.cell(145, 7, "RAZEM WYPRODUKOWANO W DNIU RAPORTU:", 1, 0, 'R', True)
        pdf.cell(20, 7, f"{total_szt} szt.", 1, 0, 'C', True)
        pdf.cell(25, 7, format_kg(total_wg), 1, 1, 'C', True)
        pdf.ln(5)

    @staticmethod
    def render_downtime(pdf, awarie_rows):
        def _rysuj_przestoje(nazwa_sekcji, tytul_naglowka, kolor_rgb):
            rows_filtered = []
            suma_minut = 0
            if awarie_rows:
                for r in awarie_rows:
                    sek = str(r[0] if len(r) > 0 and r[0] else '').strip().lower()
                    if nazwa_sekcji == 'zasyp' and 'zasyp' in sek:
                        rows_filtered.append(r)
                    elif nazwa_sekcji == 'workowanie' and ('work' in sek or 'pak' in sek or 'zasyp' not in sek):
                        rows_filtered.append(r)
            if not rows_filtered:
                return 0

            pdf.set_font("Arial", 'B', 11)
            pdf.set_fill_color(*kolor_rgb)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(0, 7, polskie_znaki_pdf(tytul_naglowka), ln=1, fill=True)
            pdf.set_text_color(0, 0, 0)
            col_dt = (32, 22, 38, 98)
            rysuj_wiersz_multicell(pdf, col_dt, ["Godziny", "Czas", "Kategoria", "Opis / Problem / Zlecenie"], col_aligns=['C', 'C', 'L', 'L'], fill=True, fill_color=(254, 226, 226), font_style='B')

            pdf.set_font("Arial", size=9)
            fill = False
            for r in rows_filtered:
                g_start = str(r[3] if len(r) > 3 and r[3] else '')[:5]
                g_stop = str(r[4] if len(r) > 4 and r[4] else '')[:5]
                godz_txt = f"{g_start} - {g_stop}" if g_start or g_stop else "-"
                try:
                    minuty_val = int(r[5]) if len(r) > 5 and r[5] is not None else 0
                except Exception:
                    minuty_val = 0
                suma_minut += minuty_val
                minuty_txt = f"{minuty_val} min" if minuty_val > 0 else "-"
                kat_txt = str(r[1] if len(r) > 1 and r[1] else 'Inne')
                opis_txt = str(r[2] if len(r) > 2 and r[2] else '')
                row_color = (254, 242, 242) if fill else (255, 255, 255)
                rysuj_wiersz_multicell(pdf, col_dt, [godz_txt, minuty_txt, kat_txt, opis_txt], col_aligns=['C', 'C', 'L', 'L'], fill=fill, fill_color=row_color, font_style='')
                fill = not fill

            pdf.set_font("Arial", 'B', 9)
            pdf.set_fill_color(254, 226, 226)
            pdf.set_text_color(185, 28, 28)
            dt_h, dt_m = suma_minut // 60, suma_minut % 60
            dt_sum_str = f"{dt_h}h {dt_m} min ({suma_minut} min)" if dt_h > 0 else f"{dt_m} min"
            pdf.cell(0, 7, polskie_znaki_pdf(f"ŁĄCZNY CZAS POSTOJU — {nazwa_sekcji.upper()}: {dt_sum_str}"), 1, 1, 'L', True)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(4)
            return suma_minut

        dt_zasyp = _rysuj_przestoje('zasyp', 'PRZESTOJE I AWARIE — ZASYP', (185, 28, 28))
        dt_work = _rysuj_przestoje('workowanie', 'PRZESTOJE I AWARIE — WORKOWANIE', (220, 38, 38))
        total_dt_min = (dt_zasyp or 0) + (dt_work or 0)
        if total_dt_min > 0:
            tot_h, tot_m = total_dt_min // 60, total_dt_min % 60
            tot_sum_str = f"{tot_h}h {tot_m} min ({total_dt_min} min)" if tot_h > 0 else f"{total_dt_min} min"
            pdf.set_font("Arial", 'B', 10)
            pdf.set_fill_color(254, 202, 202)
            pdf.set_text_color(153, 27, 27)
            pdf.cell(0, 8, polskie_znaki_pdf(f"SUMARYCZNY CZAS POSTOJU CAŁEJ ZMIANY: {tot_sum_str}"), 1, 1, 'C', True)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(4)
