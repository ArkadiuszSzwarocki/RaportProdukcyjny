import os
import pandas as pd
from fpdf import FPDF

# Upewniamy się, że folder istnieje
if not os.path.exists('raporty'):
    os.makedirs('raporty')

def format_godziny(wartosc):
    """Pomocnik do formatowania czasu"""
    if not wartosc: return "0h 0m"
    try:
        val = float(wartosc)
        h = int(val)
        m = int(round((val - h) * 60))
        return f"{h}h {m}m"
    except:
        return f"{wartosc}h"

def polskie_znaki_pdf(text):
    """Podmienia polskie znaki dla biblioteki FPDF"""
    if text is None: return ""
    text = str(text)
    replacements = {
        'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n', 'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z',
        'Ą': 'A', 'Ć': 'C', 'Ę': 'E', 'Ł': 'L', 'Ń': 'N', 'Ó': 'O', 'Ś': 'S', 'Ź': 'Z', 'Ż': 'Z'
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text

def generuj_excel(dzisiaj, prod_rows, awarie_rows, hr_rows):
    """Generuje plik Excel i zwraca jego nazwę"""
    nazwa_excel = f"Raport_{dzisiaj}.xlsx"
    sciezka = os.path.join('raporty', nazwa_excel)
    
    with pd.ExcelWriter(sciezka, engine='openpyxl') as writer:
        pd.DataFrame(prod_rows, columns=['Sekcja', 'Produkt', 'Plan', 'Wykonanie']).to_excel(writer, sheet_name='Produkcja', index=False)
        pd.DataFrame(awarie_rows, columns=['Sekcja', 'Kategoria', 'Problem', 'Start', 'Stop', 'Minuty']).to_excel(writer, sheet_name='Awarie', index=False)
        pd.DataFrame(hr_rows, columns=['Pracownik', 'Typ', 'Godziny']).to_excel(writer, sheet_name='HR', index=False)
    
    return nazwa_excel

def generuj_pdf(dzisiaj, uwagi, lider, prod_rows, awarie_rows, hr_rows):
    """Generuje plik PDF z tabelami"""
    nazwa_pdf = f"Raport_{dzisiaj}.pdf"
    sciezka = os.path.join('raporty', nazwa_pdf)
    
    pdf = FPDF()
    pdf.add_page()
    
    # --- NAGŁÓWEK ---
    pdf.set_font("Arial", 'B', 16)
    pdf.set_fill_color(44, 62, 80); pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 15, txt=polskie_znaki_pdf(f"RAPORT ZMIANY: {dzisiaj}"), ln=1, align='C', fill=True)
    
    # --- INFO LIDER ---
    pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", size=10); pdf.ln(5)
    pdf.cell(0, 8, txt=polskie_znaki_pdf(f"Lider Zmiany: {lider}"), ln=1)
    
    # --- UWAGI ---
    pdf.set_fill_color(240, 240, 240)
    pdf.multi_cell(0, 8, txt=polskie_znaki_pdf(f"UWAGI:\n{uwagi}"), fill=True)
    pdf.ln(5)

    # --- TABELA PRODUKCJA ---
    pdf.set_font("Arial", 'B', 12); pdf.set_fill_color(52, 152, 219); pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 8, "PRODUKCJA", ln=1, fill=True)
    
    # Nagłówki tabeli
    pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", 'B', 9); pdf.set_fill_color(220, 220, 220)
    pdf.cell(35, 7, "Sekcja", 1, 0, 'C', True)
    pdf.cell(90, 7, "Produkt", 1, 0, 'C', True)
    pdf.cell(30, 7, "Plan", 1, 0, 'C', True)
    pdf.cell(35, 7, "Wykonanie", 1, 1, 'C', True)
    
    # Dane tabeli
    pdf.set_font("Arial", size=9)
    fill = False
    for r in prod_rows:
        pdf.set_fill_color(245, 245, 245) if fill else pdf.set_fill_color(255, 255, 255)
        
        # Formatowanie liczb i naprawa "Nonet"
        plan_str = f"{r[2]} t" if r[2] else "-"
        wyk_str = f"{r[3]} t" if r[3] is not None else "0.0 t"

        pdf.cell(35, 7, polskie_znaki_pdf(str(r[0])), 1, 0, 'L', fill)
        pdf.cell(90, 7, polskie_znaki_pdf(str(r[1])[:45]), 1, 0, 'L', fill)
        pdf.cell(30, 7, plan_str, 1, 0, 'C', fill)
        pdf.cell(35, 7, wyk_str, 1, 1, 'C', fill)
        fill = not fill
    pdf.ln(5)

    # --- TABELA AWARIE ---
    pdf.set_font("Arial", 'B', 12); pdf.set_fill_color(231, 76, 60); pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 8, "AWARIE I POSTOJE", ln=1, fill=True)
    
    pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", size=9)
    if not awarie_rows:
        pdf.cell(0, 8, "Brak zgloszen.", 1, 1)
    else:
        pdf.set_fill_color(220, 220, 220); pdf.set_font("Arial", 'B', 9)
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
            
            # Pobieramy minuty (ostatnia kolumna z zapytania)
            minuty = str(r[5]) if len(r) > 5 and r[5] is not None else "0"
            pdf.cell(25, 7, f"{minuty} min", 1, 1, 'C', fill)
            fill = not fill
    pdf.ln(5)

    # --- TABELA HR ---
    pdf.set_font("Arial", 'B', 12); pdf.set_fill_color(46, 204, 113); pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 8, "KADRY (HR)", ln=1, fill=True)
    
    pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", size=9)
    if not hr_rows:
        pdf.cell(0, 8, "Wszyscy obecni.", 1, 1)
    else:
        pdf.set_fill_color(220, 220, 220); pdf.set_font("Arial", 'B', 9)
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

    pdf.output(sciezka)
    return nazwa_pdf