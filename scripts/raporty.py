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
    pdf.set_font("Arial", 'B', 18)
    pdf.set_fill_color(41, 128, 185)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 16, txt=polskie_znaki_pdf(f"RAPORT ZMIANY: {dzisiaj}"), ln=1, align='C', fill=True)
    pdf.ln(2)
    
    # --- INFO LIDER ---
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", size=10)
    pdf.ln(5)
    pdf.cell(0, 8, txt=polskie_znaki_pdf(f"Lider Zmiany: {lider}"), ln=1)
    
    # --- NOTATKI ZMIANOWE ---
    pdf.set_fill_color(240, 240, 240)
    # Tutaj też używamy bezpiecznej funkcji
    pdf.multi_cell(0, 8, txt=polskie_znaki_pdf(f"NOTATKI ZMIANOWE:\n{uwagi}"), fill=True)
    pdf.ln(5)

    # Zbuduj mapowanie produktów -> sekcje
    products = []
    prod_map = {}
    def _normalize_prod_name(p):
        if p is None:
            return ""
        # usuń wiodące/końcowe spacje i skompresuj wielokrotne spacje
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
            prod_map[key] = {'_display': prod} # Zapisujemy też oryginalną nazwę (z wielkością liter z pierwszego wpisu)
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

    # --- TABELA PRODUKCJA: ZASYP ---
    def _rysuj_tabele_sekcji(tytul, sekcje_klucze):
        # Sprawdź czy są dane
        has_data = False
        for prod in products:
            for s_klucz in sekcje_klucze:
                if s_klucz in prod_map.get(prod, {}):
                    has_data = True
                    break

        pdf.set_font("Arial", 'B', 12)
        pdf.set_fill_color(52, 73, 94)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 8, polskie_znaki_pdf(f"PRODUKCJA - {tytul}"), ln=1, fill=True)
        
        pdf.set_text_color(0, 0, 0)
        pdf.set_fill_color(240, 240, 240)
        pdf.set_font("Arial", 'B', 9)
        col_w = (45, 50, 20, 20, 25, 30) # Zlecenie, Produkt, Plan, Wykonanie, Start, Stop
        pdf.cell(col_w[0], 7, "Zlecenie", 1, 0, 'C', True)
        pdf.cell(col_w[1], 7, "Produkt", 1, 0, 'C', True)
        pdf.cell(col_w[2], 7, "Plan", 1, 0, 'C', True)
        pdf.cell(col_w[3], 7, "Wykonanie", 1, 0, 'C', True)
        pdf.cell(col_w[4], 7, "Start", 1, 0, 'C', True)
        pdf.cell(col_w[5], 7, "Stop", 1, 1, 'C', True)
        
        if not has_data:
            pdf.set_font("Arial", size=9)
            pdf.cell(0, 7, polskie_znaki_pdf("Brak zaplanowanej produkcji w tej sekcji."), 1, 1, 'C')
            pdf.ln(5)
            return

        pdf.set_font("Arial", size=9)
        fill = False
        for prod in products:
            # Szukamy pierwszej pasującej sekcji dla produktu
            p_data = None
            znaleziona_sekcja = None
            for s_klucz in sekcje_klucze:
                if s_klucz in prod_map.get(prod, {}):
                    p_data = prod_map[prod][s_klucz]
                    znaleziona_sekcja = s_klucz
                    break
            
            if not p_data: continue

            plan, wyk, r_start, r_stop, zlec_raw = p_data
            zlec = polskie_znaki_pdf(str(zlec_raw)[:40] if zlec_raw else "Brak")
            prod_name = polskie_znaki_pdf(str(prod_map[prod].get('_display', prod))[:28])

            try:
                pval = float(plan) if plan is not None else 0.0
            except: pval = 0.0
            try:
                wval = float(wyk) if wyk is not None else 0.0
            except: wval = 0.0

            plan_str = _fmt_kg(pval) if pval else "-"
            wyk_str = _fmt_kg(wval) if (wval or wval == 0) else "-"

            s_str = "-"
            e_str = "-"
            if r_start:
                s_str = r_start.strftime('%H:%M') if hasattr(r_start, 'strftime') else str(r_start)[:5]
            if r_stop:
                e_str = r_stop.strftime('%H:%M') if hasattr(r_stop, 'strftime') else str(r_stop)[:5]

            if fill: pdf.set_fill_color(250, 250, 250)
            else: pdf.set_fill_color(255, 255, 255)

            pdf.cell(col_w[0], 7, zlec, 1, 0, 'L', fill)
            pdf.cell(col_w[1], 7, prod_name, 1, 0, 'L', fill)
            pdf.cell(col_w[2], 7, plan_str, 1, 0, 'C', fill)
            pdf.cell(col_w[3], 7, wyk_str, 1, 0, 'C', fill)
            pdf.cell(col_w[4], 7, s_str, 1, 0, 'C', fill)
            pdf.cell(col_w[5], 7, e_str, 1, 1, 'C', fill)
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

        pdf.ln(5)

    _rysuj_tabele_sekcji('ZASYP', ['Zasyp'])
    _rysuj_tabele_sekcji('WORKOWANIE', ['Workowanie', 'Czyszczenie'])

    # --- NOWA SEKCJA: WYPRODUKOWANE PALETY ---
    palety_rows = palety_rows or []
    pdf.set_font("Arial", 'B', 12)
    pdf.set_fill_color(243, 156, 18)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 8, polskie_znaki_pdf("WYPRODUKOWANE PALETY (W DNIU RAPORTU)"), ln=1, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", size=9)
    pdf.ln(2)
    if not palety_rows:
        pdf.cell(0, 7, "Brak wyprodukowanych palet w tym dniu.", 1, 1)
    else:
        pdf.set_fill_color(230, 230, 230)
        pdf.set_font("Arial", 'B', 9)
        pdf.cell(75, 7, "Zlecenie", 1, 0, 'L', True)
        pdf.cell(65, 7, "Produkt", 1, 0, 'L', True)
        pdf.cell(25, 7, "Sztuk", 1, 0, 'C', True)
        pdf.cell(25, 7, "Waga", 1, 1, 'C', True)
        
        fill = False
        pdf.set_font("Arial", size=9)
        total_szt = 0
        total_wg = 0.0
        for r in palety_rows:
            pdf.set_fill_color(250, 250, 250) if fill else pdf.set_fill_color(255, 255, 255)
            zlec = polskie_znaki_pdf(str(r[0])[:35] if r[0] else "Brak")
            prod = polskie_znaki_pdf(str(r[1])[:30] if r[1] else "Brak")
            szt = int(r[2]) if r[2] else 0
            wg = float(r[3]) if r[3] else 0.0
            
            total_szt += szt
            total_wg += wg
            
            pdf.cell(75, 7, zlec, 1, 0, 'L', fill)
            pdf.cell(65, 7, prod, 1, 0, 'L', fill)
            pdf.cell(25, 7, f"{szt} szt.", 1, 0, 'C', fill)
            pdf.cell(25, 7, _fmt_kg(wg), 1, 1, 'C', fill)
            fill = not fill
            
        pdf.set_font("Arial", 'B', 9)
        pdf.set_fill_color(250, 235, 215)
        pdf.cell(140, 7, "RAZEM WYPRODUKOWANO W DNIU RAPORTU:", 1, 0, 'R', True)
        pdf.cell(25, 7, f"{total_szt} szt.", 1, 0, 'C', True)
        pdf.cell(25, 7, _fmt_kg(total_wg), 1, 1, 'C', True)
        
    pdf.ln(5)

    # --- TABELA AWARIE I PRZESTOJE ---
    pdf.set_font("Arial", 'B', 12)
    pdf.set_fill_color(192, 57, 43)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 8, "AWARIE I POSTOJE", ln=1, fill=True)
    
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", size=9)
    if not awarie_rows:
        pdf.cell(0, 8, "Brak zgloszen.", 1, 1)
    else:
        pdf.set_fill_color(220, 220, 220)
        pdf.set_font("Arial", 'B', 9)
        pdf.cell(35, 7, "Sekcja/Kat.", 1, 0, 'L', True)
        pdf.cell(90, 7, "Opis Problemu", 1, 0, 'L', True)
        pdf.cell(40, 7, "Czas", 1, 0, 'C', True)
        pdf.cell(25, 7, "Minuty", 1, 1, 'C', True)
        
        pdf.set_font("Arial", size=9)
        fill = False
        for r in awarie_rows:
            pdf.set_fill_color(245, 245, 245) if fill else pdf.set_fill_color(255, 255, 255)
            # r: [sekcja, kat, problem, start, stop, minuty]
            pdf.cell(35, 7, polskie_znaki_pdf(f"{r[0]} ({r[1]})"), 1, 0, 'L', fill)
            pdf.cell(90, 7, polskie_znaki_pdf(str(r[2])[:50]), 1, 0, 'L', fill)
            pdf.cell(40, 7, f"{r[3]} - {r[4]}", 1, 0, 'C', fill)
            
            # Pobieramy minuty
            minuty = str(r[5]) if len(r) > 5 and r[5] is not None else "0"
            pdf.cell(25, 7, f"{minuty} min", 1, 1, 'C', fill)
            fill = not fill
    pdf.ln(5)

    # --- TABELA HR ---
    pdf.set_font("Arial", 'B', 12)
    pdf.set_fill_color(39, 174, 96)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 8, "KADRY (HR)", ln=1, fill=True)
    
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", size=9)
    if not hr_rows:
        pdf.cell(0, 8, "Wszyscy obecni.", 1, 1)
    else:
        pdf.set_fill_color(220, 220, 220)
        pdf.set_font("Arial", 'B', 9)
        pdf.cell(70, 7, "Pracownik", 1, 0, 'L', True)
        pdf.cell(60, 7, "Typ", 1, 0, 'L', True)
        pdf.cell(60, 7, "Czas", 1, 1, 'C', True)
        
        pdf.set_font("Arial", size=9)
        fill = False
        for r in hr_rows:
            pdf.set_fill_color(245, 245, 245) if fill else pdf.set_fill_color(255, 255, 255)
            pdf.cell(70, 7, polskie_znaki_pdf(str(r[0])), 1, 0, 'L', fill)
            pdf.cell(60, 7, polskie_znaki_pdf(str(r[1])), 1, 0, 'L', fill)
            pdf.cell(60, 7, format_godziny(r[2]), 1, 1, 'C', fill)
            fill = not fill

    # --- SEKCJA: OBSADA ---
    obsada_rows = obsada_rows or []
    pdf.set_font("Arial", 'B', 12)
    pdf.set_fill_color(26, 82, 118)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 8, "OBSADA ZMIANY - SEKCJE", ln=1, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", size=9)
    pdf.ln(2)
    if not obsada_rows:
        pdf.cell(0, 7, "Brak danych o obsadzie.", 1, 1)
    else:
        # Grupuj po sekcji
        from collections import defaultdict
        sekcje_obsady = defaultdict(list)
        for sec, osoba in obsada_rows:
            sekcje_obsady[sec].append(osoba)
        for sec in sorted(sekcje_obsady.keys()):
            pdf.set_font("Arial", 'B', 10)
            pdf.set_fill_color(200, 220, 240)
            pdf.cell(0, 7, polskie_znaki_pdf(f"  {sec} ({len(sekcje_obsady[sec])} os.)"), 1, 1, 'L', True)
            pdf.set_font("Arial", size=9)
            for osoba in sekcje_obsady[sec]:
                pdf.cell(0, 6, polskie_znaki_pdf(f"      - {osoba}"), 0, 1, 'L')
    pdf.ln(4)

    # --- SEKCJA: NIEOBECNI ---
    nieobecni_rows = nieobecni_rows or []
    pdf.set_font("Arial", 'B', 12)
    pdf.set_fill_color(142, 68, 173)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 8, "NIEOBECNOSCI", ln=1, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", size=9)
    pdf.ln(2)
    if not nieobecni_rows:
        pdf.cell(0, 7, "Brak nieobecnosci.", 1, 1)
    else:
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
    pdf.set_font("Arial", 'B', 12)
    pdf.set_fill_color(23, 32, 42)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 8, "NADGODZINY", ln=1, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", size=9)
    pdf.ln(2)
    if not nadgodziny_rows:
        pdf.cell(0, 7, "Brak nadgodzin w tej zmianie.", 1, 1)
    else:
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