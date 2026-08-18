import os
from pathlib import Path

# Opóźnione importy ciężkich zależności (pandas, fpdf)

# Upewniamy się, że folder istnieje (relatywnie do katalogu repo)
base_dir = Path(__file__).resolve().parent.parent
RAPORTY_PATH = str(base_dir / 'raporty')
try:
    Path(RAPORTY_PATH).mkdir(parents=True, exist_ok=True)
except PermissionError:
    # Nie przerywamy importu aplikacji z powodu braku uprawnień do utworzenia katalogu.
    # Logowanie jest bezpieczne jeśli moduł logging jest dostępny.
    try:
        import logging
        logging.getLogger(__name__).warning("Nie udało się utworzyć katalogu 'raporty' (brak uprawnień)")
    except Exception:
        pass

def format_godziny(wartosc):
    """Pomocnik do formatowania czasu"""
    if not wartosc: return "0h 0m"
    try:
        val = float(wartosc)
        h = int(val)
        m = int(round((val - h) * 60))
        return f"{h}h {m}m"
    except Exception:
        return f"{wartosc}h"

def polskie_znaki_pdf(text):
    """
    Podmienia polskie znaki i znaki specjalne dla biblioteki FPDF.
    Zapobiega błędom 'UnicodeEncodeError'.
    """
    if text is None: return ""
    text = str(text)
    
    # 1. Mapa zamienników (Polskie znaki + znaki typograficzne z Worda/Excela)
    replacements = {
        # Polskie
        'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n', 'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z',
        'Ą': 'A', 'Ć': 'C', 'Ę': 'E', 'Ł': 'L', 'Ń': 'N', 'Ó': 'O', 'Ś': 'S', 'Ź': 'Z', 'Ż': 'Z',
        # Specjalne (To one powodowały błąd!)
        '\u2013': '-',  # Półpauza (Długi myślnik)
        '\u2014': '-',  # Pauza (Bardzo długi myślnik)
        '\u201c': '"',  # Cudzysłów otwierający
        '\u201d': '"',  # Cudzysłów zamykający
        '”': '"', '„': '"', '’': "'"
    }
    
    for k, v in replacements.items():
        text = text.replace(k, v)
    
    # 2. OSTATNIA DESKA RATUNKU
    # Jeśli jakiś znak nadal nie pasuje do Latin-1 (np. emotikona), zamień go na "?"
    # Dzięki temu system NIGDY się nie wyłączy przez błąd czcionki.
    return text.encode('latin-1', 'replace').decode('latin-1')

def generuj_excel(dzisiaj, prod_rows, awarie_rows, hr_rows):
    """Generuje plik Excel i zwraca jego nazwę"""
    nazwa_excel = f"Raport_{dzisiaj}.xlsx"
    sciezka = os.path.join(RAPORTY_PATH, nazwa_excel)
    # importujemy pandas tylko podczas generowania excela (unikamy ciężkiego importu przy starcie aplikacji)
    import pandas as pd

    with pd.ExcelWriter(sciezka, engine='openpyxl') as writer:
        pd.DataFrame(prod_rows, columns=['Sekcja', 'Produkt', 'Plan', 'Wykonanie']).to_excel(writer, sheet_name='Produkcja', index=False)
        pd.DataFrame(awarie_rows, columns=['Sekcja', 'Kategoria', 'Problem', 'Start', 'Stop', 'Minuty']).to_excel(writer, sheet_name='Awarie', index=False)
        pd.DataFrame(hr_rows, columns=['Pracownik', 'Typ', 'Godziny']).to_excel(writer, sheet_name='HR', index=False)

    return nazwa_excel

def generuj_pdf(dzisiaj, uwagi, lider, prod_rows, awarie_rows, hr_rows,
                folder, linia='PSD', obsada_rows=None, nieobecni_rows=None,
                bufor_rows=None, nadgodziny_rows=None, palety_rows=None):
    """Generuje plik PDF z tabelami"""
    nazwa_pdf = f"Raport_{dzisiaj}.pdf"
    
    sciezka = os.path.join(RAPORTY_PATH, nazwa_pdf)
    print(f"[RAPORTY.generuj_pdf] START: dzisiaj={dzisiaj}, sciezka={sciezka}")
    # importujemy FPDF tylko podczas generowania PDF (unikamy importu przy starcie aplikacji)
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()

    # Ogólne ustawienia linii
    pdf.set_draw_color(80, 80, 80)
    pdf.set_line_width(0.35)

    # --- NAGŁÓWEK ---
    pdf.set_font("Arial", 'B', 16)
    pdf.set_fill_color(41, 128, 185)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 12, txt=polskie_znaki_pdf(f"RAPORT ZMIANY: {dzisiaj}"), ln=1, align='C', fill=True)
    pdf.ln(3)
    
    # --- INFO LIDER ---
    lider_clean = str(lider or '').lstrip('|').strip()
    pdf.set_text_color(30, 41, 59)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 6, txt=polskie_znaki_pdf(f"Lider Zmiany: {lider_clean}"), ln=1)
    pdf.ln(1)
    
    czyste_uwagi = (uwagi or "").replace("NOTATKI ZMIANOWE:\n", "").replace("-" * 50 + "\n", "").lstrip('|').strip()
    if czyste_uwagi and czyste_uwagi.lower() != "brak uwag i notatek lidera.":
        # --- NOTATKI ZMIANOWE ---
        pdf.set_font("Arial", 'B', 10)
        pdf.set_fill_color(226, 232, 240)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(0, 6, txt=polskie_znaki_pdf("NOTATKI I UWAGI ZMIANOWE:"), ln=1, fill=True)
        
        pdf.set_text_color(30, 41, 59)
        pdf.set_font("Arial", size=9)
        pdf.set_fill_color(248, 250, 252)
        pdf.multi_cell(0, 6, txt=polskie_znaki_pdf(czyste_uwagi), border=1, fill=True)
        pdf.ln(4)

    # Zbuduj mapowanie produktów -> sekcje
    products = []
    prod_map = {}
    def _normalize_prod_name(p):
        if p is None:
            return ""
        return ' '.join(str(p).strip().split())

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

        key = _normalize_prod_name(prod)
        if key not in prod_map:
            prod_map[key] = {'_display': prod}
            products.append(key)
        prod_map[key][sec] = (plan, wyk, r_start, r_stop, zlec)

    import math

    def _fmt_kg(v):
        try:
            if v is None:
                return "-"
            val = float(v)
            if math.isnan(val):
                return "-"
            if abs(val - int(val)) < 1e-9:
                return f"{int(val)} kg"
            return f"{round(val, 1)} kg"
        except Exception:
            return str(v)

    # --- UNIWERSALNY RENDERER WIERSZY TABELI Z AUTO-DOSTOSOWANIEM WYSOKOŚCI ---
    def _rysuj_wiersz_multicell(col_widths, col_texts, col_aligns=None, fill=False, fill_color=(255, 255, 255), line_h=4.5, font_style=''):
        if col_aligns is None:
            col_aligns = ['L'] * len(col_widths)
        
        pdf.set_font("Arial", font_style, pdf.font_size_pt)
        
        all_cell_lines = []
        max_lines = 1
        for w, text in zip(col_widths, col_texts):
            clean_str = polskie_znaki_pdf(str(text) if text is not None else "")
            paragraphs = clean_str.replace('\r', '').split('\n')
            final_lines = []
            for paragraph in paragraphs:
                p_words = paragraph.split(' ')
                cur_line = ""
                for pw in p_words:
                    if not pw: continue
                    test_str = (cur_line + " " + pw).strip() if cur_line else pw
                    if pdf.get_string_width(test_str) <= (w - 3):
                        cur_line = test_str
                    else:
                        if cur_line:
                            final_lines.append(cur_line)
                        cur_line = pw
                if cur_line:
                    final_lines.append(cur_line)
            if not final_lines:
                final_lines = [""]
            all_cell_lines.append(final_lines)
            if len(final_lines) > max_lines:
                max_lines = len(final_lines)

        row_h = max(max_lines * line_h + 2, 7)

        if pdf.get_y() + row_h > 275:
            pdf.add_page()

        x0 = pdf.get_x()
        y0 = pdf.get_y()

        cx = x0
        for w, lines, align in zip(col_widths, all_cell_lines, col_aligns):
            if fill:
                pdf.set_fill_color(*fill_color)
                pdf.rect(cx, y0, w, row_h, 'DF')
            else:
                pdf.rect(cx, y0, w, row_h, 'D')
            
            text_block_h = len(lines) * line_h
            start_y = y0 + (row_h - text_block_h) / 2
            for i, line_txt in enumerate(lines):
                pdf.set_xy(cx + 1.5, start_y + i * line_h)
                pdf.cell(w - 3, line_h, line_txt, border=0, align=align)
            cx += w

        pdf.set_xy(x0, y0 + row_h)

    # --- TABELA PRODUKCJA: ZASYP / WORKOWANIE ---
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
        col_w = (42, 58, 22, 22, 23, 23) # Razem = 190
        
        _rysuj_wiersz_multicell(
            col_w,
            ["Zlecenie", "Produkt", "Plan", "Wykonanie", "Start", "Stop"],
            col_aligns=['C', 'C', 'C', 'C', 'C', 'C'],
            fill=True,
            fill_color=(240, 240, 240),
            font_style='B'
        )

        pdf.set_font("Arial", size=9)
        fill = False
        for prod in products:
            p_data = None
            znaleziona_sekcja = None
            for s_klucz in sekcje_klucze:
                if s_klucz in prod_map.get(prod, {}):
                    p_data = prod_map[prod][s_klucz]
                    znaleziona_sekcja = s_klucz
                    break
            
            if not p_data: continue

            plan, wyk, r_start, r_stop, zlec_raw = p_data
            zlec = str(zlec_raw) if zlec_raw else "Brak"
            prod_name = str(prod_map[prod].get('_display', prod))

            try:
                pval = float(plan) if plan is not None else 0.0
            except: pval = 0.0
            try:
                wval = float(wyk) if wyk is not None else 0.0
            except: wval = 0.0

            # Dla sekcji Workowanie planem jest rzeczywiste wykonanie zasypu
            if tytul == 'WORKOWANIE':
                try:
                    z_wyk_raw = prod_map.get(prod, {}).get('Zasyp', (None, None))[1]
                    if z_wyk_raw is not None:
                        z_val = float(z_wyk_raw)
                        if not math.isnan(z_val) and z_val > 0:
                            pval = z_val
                except Exception:
                    pass

            plan_str = _fmt_kg(pval) if pval else "-"
            wyk_str = _fmt_kg(wval) if (wval or wval == 0) else "-"

            s_str = "-"
            e_str = "-"
            if r_start:
                s_str = r_start.strftime('%H:%M') if hasattr(r_start, 'strftime') else str(r_start)[:5]
            if r_stop:
                e_str = r_stop.strftime('%H:%M') if hasattr(r_stop, 'strftime') else str(r_stop)[:5]

            row_color = (250, 250, 250) if fill else (255, 255, 255)
            _rysuj_wiersz_multicell(
                col_w,
                [zlec, prod_name, plan_str, wyk_str, s_str, e_str],
                col_aligns=['L', 'L', 'C', 'C', 'C', 'C'],
                fill=fill,
                fill_color=row_color,
                font_style=''
            )
            fill = not fill

            # Różnica dla workowania (porównanie z zasypem)
            if tytul == 'WORKOWANIE':
                try:
                    z_wyk_raw = prod_map.get(prod, {}).get('Zasyp', (None, None))[1]
                    z_plan = float(z_wyk_raw) if z_wyk_raw is not None else 0.0
                    if math.isnan(z_plan): z_plan = 0.0
                except: z_plan = 0.0
                diff = wval - z_plan
                diff_sign = '+' if diff >= 0 else '-'
                diff_abs = abs(diff)
                if math.isclose(diff_abs, round(diff_abs), abs_tol=1e-9):
                    diff_str = f"{diff_sign}{int(round(diff_abs))} kg"
                else:
                    diff_str = f"{diff_sign}{round(diff_abs,1):.1f} kg"
                
                pdf.set_font("Arial", 'B', 8)
                if diff >= 0: pdf.set_text_color(34, 139, 34)
                else: pdf.set_text_color(192, 57, 43)
                pdf.cell(190, 5, polskie_znaki_pdf(f"Rozliczenie względem zasypu: {diff_str}"), 1, 1, 'R', True)
                pdf.set_text_color(0, 0, 0)
                pdf.set_font("Arial", size=9)

        # Wydajność dla Zasypu: kg / (480 min - awarie zasypu) * 60 min
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
                    except: pass
            
            awarie_zasyp_min = 0
            if awarie_rows:
                for r in awarie_rows:
                    sek = str(r[0] if len(r) > 0 and r[0] else '').strip().lower()
                    if 'zasyp' in sek:
                        try:
                            awarie_zasyp_min += int(r[5] or 0)
                        except: pass
            
            from app.services.shift_time_service import ShiftTimeService
            prod_metrics = ShiftTimeService.calculate_productivity(
                mass_kg=suma_wyk_zasyp,
                awarie_min=awarie_zasyp_min,
                date_str=str(dzisiaj)
            )
            czas_brutto_min = prod_metrics['brutto_min']
            czas_netto_min = prod_metrics['netto_min']
            wydajnosc_efektywna = prod_metrics['wydajnosc_efektywna']
            wydajnosc_rzeczywista = prod_metrics['wydajnosc_rzeczywista']
            start_str = prod_metrics['start_str']
            end_str = prod_metrics['end_str']
            
            pdf.set_font("Arial", 'B', 9)
            pdf.set_fill_color(225, 245, 235)
            pdf.set_text_color(15, 80, 45)
            info_txt1 = f"Wydajność efektywna (netto): {wydajnosc_efektywna:.1f} kg/h (wykonane w {czas_netto_min} min produkcyjnych [{czas_brutto_min} min - {awarie_zasyp_min} min awarie])"
            pdf.cell(190, 6, polskie_znaki_pdf(info_txt1), 1, 1, 'L', True)
            
            pdf.set_fill_color(238, 246, 255)
            pdf.set_text_color(20, 70, 140)
            info_txt2 = f"Wydajność rzeczywista (brutto / {start_str}–{end_str}): {wydajnosc_rzeczywista:.1f} kg/h ({_fmt_kg(suma_wyk_zasyp)} / {czas_brutto_min} min * 60)"
            pdf.cell(190, 6, polskie_znaki_pdf(info_txt2), 1, 1, 'L', True)
            
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Arial", size=9)

        pdf.ln(5)

    _rysuj_tabele_sekcji('ZASYP', ['Zasyp'])
    _rysuj_tabele_sekcji('WORKOWANIE', ['Workowanie', 'Czyszczenie'])

    # --- SEKCJA: WYPRODUKOWANE PALETY ---
    palety_rows = palety_rows or []
    if palety_rows:
        pdf.set_font("Arial", 'B', 12)
        pdf.set_fill_color(243, 156, 18)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 8, polskie_znaki_pdf("WYPRODUKOWANE PALETY (W DNIU RAPORTU)"), ln=1, fill=True)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", size=9)
        pdf.ln(2)

        col_pal = (65, 75, 25, 25) # Razem = 190
        _rysuj_wiersz_multicell(
            col_pal,
            ["Zlecenie", "Produkt", "Sztuk", "Waga"],
            col_aligns=['C', 'C', 'C', 'C'],
            fill=True,
            fill_color=(230, 230, 230),
            font_style='B'
        )
        
        fill = False
        pdf.set_font("Arial", size=9)
        total_szt = 0
        total_wg = 0.0
        for r in palety_rows:
            zlec = str(r[0]) if r[0] else "Brak"
            prod = str(r[1]) if r[1] else "Brak"
            szt = int(r[2]) if r[2] else 0
            wg = float(r[3]) if r[3] else 0.0
            
            total_szt += szt
            total_wg += wg
            
            row_color = (250, 250, 250) if fill else (255, 255, 255)
            _rysuj_wiersz_multicell(
                col_pal,
                [zlec, prod, f"{szt} szt.", _fmt_kg(wg)],
                col_aligns=['L', 'L', 'C', 'C'],
                fill=fill,
                fill_color=row_color,
                font_style=''
            )
            fill = not fill
            
        pdf.set_font("Arial", 'B', 9)
        pdf.set_fill_color(250, 235, 215)
        pdf.cell(140, 7, "RAZEM WYPRODUKOWANO W DNIU RAPORTU:", 1, 0, 'R', True)
        pdf.cell(25, 7, f"{total_szt} szt.", 1, 0, 'C', True)
        pdf.cell(25, 7, _fmt_kg(total_wg), 1, 1, 'C', True)
        pdf.ln(5)

    # --- TABELE PRZESTOJÓW I AWARII (PODZIAŁ NA ZASYP I WORKOWANIE) ---
    def _rysuj_przestoje_sekcji(nazwa_sekcji, tytul_naglowka, kolor_rgb):
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
            return  # Ukryj sekcję jeśli brak awarii

        pdf.set_font("Arial", 'B', 11)
        pdf.set_fill_color(*kolor_rgb)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 7, polskie_znaki_pdf(tytul_naglowka), ln=1, fill=True)
        pdf.set_text_color(0, 0, 0)

        col_dt = (32, 22, 38, 98) # Razem = 190
        _rysuj_wiersz_multicell(
            col_dt,
            ["Godziny", "Czas", "Kategoria", "Opis / Problem / Zlecenie"],
            col_aligns=['C', 'C', 'L', 'L'],
            fill=True,
            fill_color=(240, 240, 240),
            font_style='B'
        )

        pdf.set_font("Arial", size=9)
        fill = False
        for r in rows_filtered:
            g_start = str(r[3] if len(r) > 3 and r[3] else '')[:5]
            g_stop = str(r[4] if len(r) > 4 and r[4] else '')[:5]
            godz_txt = f"{g_start} - {g_stop}" if g_start or g_stop else "-"
            
            try:
                minuty_val = int(r[5]) if len(r) > 5 and r[5] is not None else 0
            except: minuty_val = 0
            suma_minut += minuty_val
            minuty_txt = f"{minuty_val} min" if minuty_val > 0 else "-"

            kat_txt = str(r[1] if len(r) > 1 and r[1] else 'Inne')
            opis_txt = str(r[2] if len(r) > 2 and r[2] else '')

            row_color = (250, 250, 250) if fill else (255, 255, 255)
            _rysuj_wiersz_multicell(
                col_dt,
                [godz_txt, minuty_txt, kat_txt, opis_txt],
                col_aligns=['C', 'C', 'L', 'L'],
                fill=fill,
                fill_color=row_color,
                font_style=''
            )
            fill = not fill

        # Podsumowanie czasu
        pdf.set_font("Arial", 'B', 9)
        pdf.set_fill_color(245, 245, 245)
        dt_h = suma_minut // 60
        dt_m = suma_minut % 60
        dt_sum_str = f"{dt_h}h {dt_m} min ({suma_minut} min)" if dt_h > 0 else f"{dt_m} min"
        pdf.cell(70, 6, polskie_znaki_pdf(f"ŁĄCZNY CZAS POSTOJU: {dt_sum_str}"), 1, 1, 'L', True)
        pdf.ln(4)

    _rysuj_przestoje_sekcji('zasyp', 'PRZESTOJE I AWARIE — ZASYP', (3, 105, 161))
    _rysuj_przestoje_sekcji('workowanie', 'PRZESTOJE I AWARIE — WORKOWANIE', (21, 128, 61))

    # --- SEKCJA: OBSADA STANOWISKOWA (PRZYPISANIE PRZEZ LIDERA) ---
    obsada_rows = obsada_rows or []
    from collections import defaultdict
    sekcje_obsady = defaultdict(list)
    for r in obsada_rows:
        sec = (r[0] if len(r) > 0 and r[0] else 'Inne').strip()
        osoba = (r[1] if len(r) > 1 and r[1] else '').strip()
        funkcja = f" ({r[2]})" if len(r) > 2 and r[2] else ""
        if osoba:
            sekcje_obsady[sec].append(f"{osoba}{funkcja}")

    # Jeśli są jakiekolwiek przypisania
    if any(len(osoby) > 0 for osoby in sekcje_obsady.values()):
        pdf.set_font("Arial", 'B', 11)
        pdf.set_fill_color(30, 41, 59)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 7, polskie_znaki_pdf("OBSADA STANOWISKOWA (PRZYPISANIE PRACOWNIKÓW PRZEZ LIDERA)"), ln=1, fill=True)
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
                pdf.set_fill_color(255, 255, 255) if idx % 2 != 0 else pdf.set_fill_color(248, 250, 252)
                pdf.cell(0, 6, polskie_znaki_pdf(f"     {idx}. {osoba}"), 1, 1, 'L', True)

        pdf.ln(4)

    # --- SEKCJA: NIEOBECNI ---
    nieobecni_rows = nieobecni_rows or []
    if nieobecni_rows:
        pdf.set_font("Arial", 'B', 11)
        pdf.set_fill_color(142, 68, 173)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 7, "NIEOBECNOSCI", ln=1, fill=True)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", size=9)
        pdf.set_fill_color(220, 220, 220)
        pdf.set_font("Arial", 'B', 9)
        pdf.cell(75, 7, "Pracownik", 1, 0, 'L', True)
        pdf.cell(45, 7, "Typ nieobecnosci", 1, 0, 'C', True)
        pdf.cell(70, 7, "Komentarz", 1, 1, 'L', True)
        pdf.set_font("Arial", size=9)
        fill = False
        for r in nieobecni_rows:
            pdf.set_fill_color(245, 245, 245) if fill else pdf.set_fill_color(255, 255, 255)
            pdf.cell(75, 7, polskie_znaki_pdf(str(r[0])), 1, 0, 'L', fill)
            pdf.cell(45, 7, polskie_znaki_pdf(str(r[1])), 1, 0, 'C', fill)
            pdf.cell(70, 7, polskie_znaki_pdf(str(r[2])[:40]), 1, 1, 'L', fill)
            fill = not fill
        pdf.ln(4)

    # --- SEKCJA: NADGODZINY ---
    nadgodziny_rows = nadgodziny_rows or []
    if nadgodziny_rows:
        pdf.set_font("Arial", 'B', 11)
        pdf.set_fill_color(23, 32, 42)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 7, "NADGODZINY", ln=1, fill=True)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", size=9)
        pdf.set_fill_color(220, 220, 220)
        pdf.set_font("Arial", 'B', 9)
        pdf.cell(70, 7, "Pracownik", 1, 0, 'L', True)
        pdf.cell(20, 7, "Godz.", 1, 0, 'C', True)
        pdf.cell(30, 7, "Status", 1, 0, 'C', True)
        pdf.cell(70, 7, "Powod", 1, 1, 'L', True)
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
    pdf.ln(4)

    # Jeśli plik już istnieje (np. otwarty w czytniku), spróbuj go usunąć przed zapisem.
    try:
        if os.path.exists(sciezka):
            try:
                os.remove(sciezka)
            except Exception:
                # jeśli nie można usunąć (plik zablokowany), zapisz pod tymczasową nazwą
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