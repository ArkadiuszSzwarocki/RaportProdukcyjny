import os
import sys
from fpdf import FPDF

def replace_polish(text):
    """Zamienia polskie znaki diakrytyczne na odpowiedniki ASCII dla kompatybilności fontu FPDF Helvetica."""
    pol = {
        'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n', 'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z',
        'Ą': 'A', 'Ć': 'C', 'Ę': 'E', 'Ł': 'L', 'Ń': 'N', 'Ó': 'O', 'Ś': 'S', 'Ź': 'Z', 'Ż': 'Z'
    }
    for k, v in pol.items():
        text = text.replace(k, v)
    return text

class ProcedurePDF(FPDF):
    def header(self):
        self.set_fill_color(30, 41, 59) # Dark slate header
        self.rect(0, 0, 210, 28, 'F')
        
        self.set_font('Helvetica', 'B', 15)
        self.set_text_color(255, 255, 255)
        self.set_y(6)
        self.cell(0, 8, replace_polish("PROCEDURA PODMIANY BAZY DANYCH (SRODOWISKO DOCKER)"), align='C', new_x='LMARGIN', new_y='NEXT')
        
        self.set_font('Helvetica', 'B', 9.5)
        self.set_text_color(148, 163, 184)
        self.cell(0, 6, replace_polish("Projekt: Raport Produkcyjny  |  Srodowisko: Serwer Ubuntu (Localhost)"), align='C', new_x='LMARGIN', new_y='NEXT')
        self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(148, 163, 184)
        self.cell(0, 10, replace_polish(f"Raport Produkcyjny - Procedura Podmiany Bazy Danych | Strona {self.page_no()}/{{nb}}"), align='C')

def create_pdf(output_path):
    pdf = ProcedurePDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Subtitle / Metadata Box
    pdf.set_fill_color(241, 245, 249)
    pdf.set_draw_color(203, 213, 225)
    pdf.rect(10, 32, 190, 18, 'DF')
    
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_text_color(15, 23, 42)
    pdf.set_xy(14, 35)
    pdf.cell(0, 5, replace_polish("Cel: Instrukcja krok po kroku podmiany produkcyjnej bazy danych MySQL w kontenerze Docker."), new_x='LMARGIN', new_y='NEXT')
    pdf.set_x(14)
    pdf.cell(0, 5, replace_polish("Skrypty automatyzujace: ./scripts/podmien_baze.sh [plik.sql] lub python scripts/podmien_baze.py"), new_x='LMARGIN', new_y='NEXT')
    
    pdf.ln(8)

    steps = [
        {
            "num": "KROK 1",
            "title": "Przygotowanie pliku",
            "desc": "Upewnij sie, ze nowy zrzut bazy z QNAP-a (np. nowa_baza.sql) znajduje sie w Twoim glownym katalogu projektu na Ubuntu:",
            "code": "~/raportprodukcyjny",
            "tip": "Sprawdz czy plik posiada rozszerzenie .sql oraz odpowiednie uprawnienia odczytu."
        },
        {
            "num": "KROK 2",
            "title": "Czyszczenie starego srodowiska",
            "desc": "Otworz terminal w katalogu projektu i zatrzymaj wszystkie kontenery, jednoczesnie usuwajac stary wolumen z danymi bazy. Wpisz polecenie:",
            "code": "sudo docker-compose down -v",
            "tip": "Flaga -v usuwa wolumen z danymi bazy MySQL, umozliwiajac stworzenie czystego srodowiska."
        },
        {
            "num": "KROK 3",
            "title": "Uruchomienie czystej bazy danych",
            "desc": "Podnies sam kontener bazy danych. Wpisz:",
            "code": "sudo docker-compose up -d db",
            "tip": "Wazne: Odczekaj okolo 15-20 sekund po wykonaniu tego polecenia, aby serwer MySQL zdazyl w pelni wystartowac i zainicjowac pliki."
        },
        {
            "num": "KROK 4",
            "title": "Import nowych danych",
            "desc": "Stworz czysta strukture bazy o nazwie biblioteka i wgraj do niej nowy plik SQL. Wykonaj kolejno te dwa polecenia:",
            "code": "sudo docker-compose exec -T db mysql -u root -p'VVezyr$$' -e \"CREATE DATABASE IF NOT EXISTS biblioteka;\"\nsudo docker-compose exec -T db mysql -u root -p'VVezyr$$' biblioteka < nowa_baza.sql",
            "tip": "Uwaga: upewnij sie, ze nazwa pliku na koncu drugiego polecenia zgadza sie z nazwa Twojego pliku."
        },
        {
            "num": "KROK 5",
            "title": "Uruchomienie aplikacji",
            "desc": "Gdy import zakonczy sie bez bledow, uruchom kontener z aplikacja:",
            "code": "sudo docker-compose up -d app",
            "tip": "Aplikacja automatycznie polaczy sie ze swiezo zainicjowana i zaimportowana baza danych."
        },
        {
            "num": "KROK 6",
            "title": "Weryfikacja",
            "desc": "Wejdz do przegladarki pod adres:\nhttps://localhost:5005\nZaloguj sie i sprawdz, czy nowe dane sa widoczne. Procedura zakonczona!",
            "code": "https://localhost:5005",
            "tip": "Sprawdz poprawnosc zalogowania, stany magazynowe oraz ostatnie zlecenia produkcyjne."
        }
    ]

    for step in steps:
        # Step Header Pill
        pdf.set_fill_color(16, 185, 129) # Emerald Green pill
        pdf.set_text_color(255, 255, 255)
        pdf.set_font('Helvetica', 'B', 9.5)
        pdf.cell(24, 6.5, f"  {step['num']}  ", fill=True, new_x='RIGHT', new_y='TOP')
        
        pdf.set_text_color(15, 23, 42)
        pdf.set_font('Helvetica', 'B', 11)
        pdf.cell(0, 6.5, f"  {replace_polish(step['title'])}", new_x='LMARGIN', new_y='NEXT')
        pdf.ln(1)
        
        # Step Description
        pdf.set_font('Helvetica', '', 9.5)
        pdf.set_text_color(51, 65, 85)
        pdf.multi_cell(0, 4.8, replace_polish(step['desc']))
        pdf.ln(2)
        
        # Code Box
        pdf.set_fill_color(248, 250, 252)
        pdf.set_draw_color(203, 213, 225)
        pdf.set_font('Courier', 'B', 9)
        pdf.set_text_color(15, 23, 42)
        
        code_lines = step['code'].split('\n')
        box_height = len(code_lines) * 5.5 + 4
        
        cur_y = pdf.get_y()
        pdf.rect(10, cur_y, 190, box_height, 'DF')
        pdf.set_xy(14, cur_y + 2)
        
        for line in code_lines:
            pdf.cell(0, 5.5, replace_polish(line), new_x='LMARGIN', new_y='NEXT')
            pdf.set_x(14)
            
        pdf.set_y(cur_y + box_height + 2)
        
        # Tip
        pdf.set_font('Helvetica', 'I', 8.5)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(0, 4.5, replace_polish(f"Wskazowka: {step['tip']}"), new_x='LMARGIN', new_y='NEXT')
        pdf.ln(4)

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pdf.output(output_path)
    print(f"Wygenerowano dokument PDF: {output_path}")

if __name__ == '__main__':
    doc_path = os.path.join(os.getcwd(), 'docs', 'Procedura_Podmiany_Bazy_Danych.pdf')
    create_pdf(doc_path)
    
    # Also save a copy to the artifacts directory
    artifact_dir = r"C:\Users\arkad\.gemini\antigravity-ide\brain\8cc29328-0624-478d-9a35-a00e9dca800f"
    if os.path.exists(artifact_dir):
        artifact_pdf = os.path.join(artifact_dir, 'Procedura_Podmiany_Bazy_Danych.pdf')
        create_pdf(artifact_pdf)
