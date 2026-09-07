#!/usr/bin/env python3
"""
Script do połączenia wszystkich dokumentów MQTT w jeden PDF
Użycie: python create_mqtt_pdf.py
"""

import os
from pathlib import Path
from datetime import datetime

# Ścieżka do głównego folderu
REPO_ROOT = Path(__file__).parent
OUTPUT_FILE = REPO_ROOT / "MQTT_COMPLETE_DOCUMENTATION.md"

# Lista plików do połączenia w kolejności
FILES_TO_MERGE = [
    "MQTT_README.md",
    "MQTT_QUICK_REFERENCE.md",
    "MQTT_ARCHITECTURE.md",
    "MQTT_FAQ.md",
    "MQTT_DOCUMENTATION.md",
    "MQTT_INDEX.md",
]

# Dodatkowo - kod Python
PYTHON_FILES = [
    "mqtt_test_suite.py",
]

def merge_markdown_files():
    """Łączy wszystkie pliki markdown w jeden"""
    
    print("📝 Łączenie plików dokumentacji...")
    print("-" * 60)
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as outfile:
        # Header
        outfile.write("# 📡 MQTT COMPLETE DOCUMENTATION\n\n")
        outfile.write(f"**Wygenerowano:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        outfile.write("**Zawartość:**\n")
        outfile.write("1. MQTT README – Spis dokumentacji\n")
        outfile.write("2. MQTT Quick Reference – Szybka ściągawka\n")
        outfile.write("3. MQTT Architecture – Architektura systemu\n")
        outfile.write("4. MQTT FAQ – Pytania i odpowiedzi\n")
        outfile.write("5. MQTT Documentation – Pełna dokumentacja\n")
        outfile.write("6. MQTT Index – Indeks tematyczny\n")
        outfile.write("7. Test Suite – Kod testowy\n\n")
        outfile.write("---\n\n")
        
        # Łącz pliki markdown
        for filename in FILES_TO_MERGE:
            filepath = REPO_ROOT / filename
            if filepath.exists():
                print(f"  ✅ Dodaję: {filename}")
                outfile.write(f"\n<!-- ==================== PAGE BREAK ==================== -->\n\n")
                
                with open(filepath, 'r', encoding='utf-8') as infile:
                    content = infile.read()
                    outfile.write(content)
                    outfile.write("\n\n")
            else:
                print(f"  ⚠️  Brak pliku: {filename}")
        
        # Dodaj kod Python jako listing
        outfile.write("\n\n<!-- ==================== PAGE BREAK ==================== -->\n\n")
        outfile.write("# 🧪 Test Suite – Kod Aplikacji\n\n")
        
        for filename in PYTHON_FILES:
            filepath = REPO_ROOT / filename
            if filepath.exists():
                print(f"  ✅ Dodaję kod: {filename}")
                outfile.write(f"\n## {filename}\n\n")
                outfile.write("```python\n")
                
                with open(filepath, 'r', encoding='utf-8') as infile:
                    content = infile.read()
                    outfile.write(content)
                
                outfile.write("\n```\n\n")
            else:
                print(f"  ⚠️  Brak pliku: {filename}")
    
    print("-" * 60)
    print(f"✅ Plik połączony: {OUTPUT_FILE}")
    print(f"   Rozmiar: {OUTPUT_FILE.stat().st_size / 1024:.1f} KB")
    return True

def convert_to_pdf():
    """Konwertuje markdown na PDF"""
    print("\n📄 Konwertowanie na PDF...")
    print("-" * 60)
    
    pdf_file = REPO_ROOT / "MQTT_COMPLETE_DOCUMENTATION.pdf"
    
    try:
        from markdown2pdf import Markdown2PDF
        
        converter = Markdown2PDF(
            filename=str(OUTPUT_FILE),
            output_filename=str(pdf_file),
        )
        converter.convert()
        
        print(f"✅ PDF utworzony: {pdf_file}")
        print(f"   Rozmiar: {pdf_file.stat().st_size / (1024*1024):.1f} MB")
        return True
        
    except Exception as e:
        print(f"❌ Błąd konwersji: {e}")
        print("\n💡 Próbuję alternatywną metodę (weasyprint)...")
        
        try:
            from weasyprint import HTML
            
            HTML(string=_markdown_to_html(OUTPUT_FILE)).write_pdf(str(pdf_file))
            
            print(f"✅ PDF utworzony (weasyprint): {pdf_file}")
            print(f"   Rozmiar: {pdf_file.stat().st_size / (1024*1024):.1f} MB")
            return True
            
        except Exception as e2:
            print(f"❌ Błąd weasyprint: {e2}")
            return False

def _markdown_to_html(markdown_file):
    """Konwertuje markdown na HTML"""
    try:
        import markdown
        
        with open(markdown_file, 'r', encoding='utf-8') as f:
            md_content = f.read()
        
        html = markdown.markdown(md_content, extensions=['extra', 'toc'])
        
        # Dodaj CSS styling
        full_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; max-width: 900px; margin: 40px; }}
                h1 {{ color: #0066cc; border-bottom: 2px solid #0066cc; padding-bottom: 10px; }}
                h2 {{ color: #0066cc; margin-top: 30px; }}
                h3 {{ color: #333; }}
                code {{ background: #f4f4f4; padding: 2px 5px; border-radius: 3px; font-family: monospace; }}
                pre {{ background: #f4f4f4; padding: 15px; border-left: 3px solid #0066cc; overflow-x: auto; }}
                pre code {{ background: none; padding: 0; }}
                table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
                table td, table th {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
                table th {{ background-color: #0066cc; color: white; }}
                blockquote {{ border-left: 4px solid #0066cc; margin: 0; padding-left: 15px; color: #666; }}
                a {{ color: #0066cc; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
                page-break-after: always; {{ page-break-after: always; }}
            </style>
        </head>
        <body>
            {html}
        </body>
        </html>
        """
        
        return full_html
    except Exception as e:
        print(f"Błąd konwersji markdown→HTML: {e}")
        return None

def main():
    print("\n" + "=" * 60)
    print("🚀 MQTT DOCUMENTATION – PDF CREATOR")
    print("=" * 60)
    
    # Krok 1: Połącz pliki
    if not merge_markdown_files():
        print("❌ Nie udało się połączyć plików!")
        return False
    
    # Krok 2: Konwertuj na PDF
    if not convert_to_pdf():
        print("❌ Nie udało się konwertować na PDF!")
        print("\n💡 Alternatywy:")
        print("   1. Zainstaluj pandoc: choco install pandoc")
        print("   2. Użyj online: https://markdowntopdf.com/")
        print("   3. Plik markdown jest gotowy: MQTT_COMPLETE_DOCUMENTATION.md")
        return False
    
    print("\n" + "=" * 60)
    print("✅ GOTOWE!")
    print("=" * 60)
    print(f"\n📄 Pliki:")
    print(f"   Markdown: {OUTPUT_FILE}")
    print(f"   PDF:      {REPO_ROOT / 'MQTT_COMPLETE_DOCUMENTATION.pdf'}")
    
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
