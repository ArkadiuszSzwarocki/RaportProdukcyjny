"""
Serwis generowania kodów QR i etykiet magazynowych (tekst, lokalizacje, loginy).
Obsługuje wymiary etykiet (domyślnie 80x80 mm), generowanie ZPL oraz katalog wszystkich lokalizacji.
"""
from typing import List, Dict, Any, Optional, Tuple
import re
import json
from app.db import get_db_connection


class QrGeneratorService:
    DEFAULT_WIDTH_MM = 80
    DEFAULT_HEIGHT_MM = 80
    DEFAULT_DPI = 203

    @classmethod
    def get_all_warehouse_locations(cls) -> Dict[str, Any]:
        """
        Zwraca pełny, skategoryzowany katalog wszystkich lokalizacji w systemie:
        - Magazyny główne i strefy otwarte
        - Regały wysokiego składowania R01-R07 oraz regał półkowy R09
        - Alejki magazynu OSIP (OS01-OS77)
        - Stacje produkcyjne (KO01-KO24, BB01-BB24, MZ07-MZ24)
        - Własne lokalizacje ze słownika dozwolonych lokalizacji
        """
        categories: Dict[str, List[Dict[str, str]]] = {
            'magazyny': [],
            'regaly': [],
            'osip': [],
            'stacje': [],
            'wlasne': []
        }

        # 1. Główne strefy i magazyny
        main_zones = [
            ('MS01', 'Magazyn Surowcowy', 'Centrala (Hala PSD/Surowce)'),
            ('MP01', 'Magazyn Produkcyjny', 'Centrala (Hala Produkcyjna)'),
            ('MGW01', 'Magazyn Wyrobów Gotowych 1', 'Hala Wyrobów Gotowych'),
            ('MGW02', 'Magazyn Wyrobów Gotowych 2', 'Hala Wyrobów Gotowych'),
            ('OSIP', 'Magazyn Zewnętrzny OSIP', 'Oddział OSIP'),
            ('PSD01', 'Magazyn Produkcyjny PSD', 'Linia PSD'),
            ('MDO01', 'Magazyn Dodatków (MDO)', 'Strefa Dodatków'),
            ('MDM01', 'Magazyn Dodatków Mikro', 'Strefa Mikrodozowania'),
            ('MOP01', 'Magazyn Opakowań', 'Strefa Opakowań'),
            ('BF_MS01', 'Bufor Magazynu Surowców', 'Strefa Buforowa MS01'),
            ('BF_MP01', 'Bufor Magazynu Produkcji', 'Strefa Buforowa MP01'),
            ('BFOS', 'Bufor Magazynu OSIP', 'Strefa Buforowa OSIP'),
            ('RAMPA', 'Rampa Załadunkowo-Rozładunkowa', 'Strefa Przyjęć/Wydań'),
            ('MIX01', 'Strefa Mixowania Palet', 'Strefa Przygotowania'),
            ('W_TRANZYCIE_OSIP', 'W Tranzycie OSIP', 'Status Międzymagazynowy'),
            ('LP01', 'Stanowisko Pakowania LP01', 'Linia Agro LP01')
        ]
        for code, name, zone in main_zones:
            categories['magazyny'].append({
                'code': code,
                'name': name,
                'zone': zone,
                'category': 'Magazyny & Strefy'
            })

        # 2. Regały wysokiego składowania R01-R07 oraz R09
        for rack_no in range(1, 8):
            rack_prefix = f"R{rack_no:02d}"
            max_places = 6 if rack_prefix == 'R04' else (11 if rack_prefix == 'R07' else 10)
            max_rows = 4 if rack_prefix == 'R07' else 3
            for place in range(1, max_places + 1):
                for row in range(1, max_rows + 1):
                    code = f"{rack_prefix}{place:02d}{row:02d}"
                    categories['regaly'].append({
                        'code': code,
                        'name': f"Regał {rack_prefix} (M:{place:02d}, P:{row:02d})",
                        'zone': f"Regał {rack_prefix}",
                        'category': 'Regały Wysokiego Składowania'
                    })

        # Regał półkowy R09: 4 miejsca x 6 poziomów
        for place in range(1, 5):
            for row in range(1, 7):
                code = f"R09{place:02d}{row:02d}"
                categories['regaly'].append({
                    'code': code,
                    'name': f"Regał Półkowy R09 (M:{place:02d}, P:{row:02d})",
                    'zone': "Regał Półkowy R09",
                    'category': 'Regały Półkowe'
                })

        # 3. Alejki magazynu OSIP (OS01-OS77)
        for idx in range(1, 78):
            code = f"OS{idx:02d}"
            categories['osip'].append({
                'code': code,
                'name': f"Alejka OSIP #{idx:02d}",
                'zone': "Magazyn OSIP",
                'category': 'Alejki OSIP'
            })

        # 4. Stacje produkcyjne & Big Bagi
        for idx in range(1, 25):
            code_ko = f"KO{idx:02d}"
            categories['stacje'].append({
                'code': code_ko,
                'name': f"Stacja Koszowa {code_ko}",
                'zone': "Hala Produkcyjna / Zasyp",
                'category': 'Stacje Produkcyjne'
            })
            if idx not in (7, 8, 9, 10, 23, 24):
                code_bb = f"BB{idx:02d}"
                categories['stacje'].append({
                    'code': code_bb,
                    'name': f"Stacja Big Bag {code_bb}",
                    'zone': "Hala Produkcyjna / Big Bag",
                    'category': 'Stacje Big Bag'
                })

        for idx in (7, 8, 9, 10, 23, 24):
            code_mz = f"MZ{idx:02d}"
            categories['stacje'].append({
                'code': code_mz,
                'name': f"Zbiornik / Mieszalnik {code_mz}",
                'zone': "Hala Produkcyjna / Mieszalniki",
                'category': 'Zbiorniki Produkcyjne'
            })

        # 5. Własne lokalizacje z bazy danych
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT id, nazwa, opis FROM magazyn_dozwolone_lokalizacje ORDER BY nazwa ASC")
            rows = cur.fetchall() or []
            existing_codes = {item['code'] for sub in categories.values() for item in sub}
            for r in rows:
                code = str(r.get('nazwa') or '').strip().upper()
                if code and code not in existing_codes:
                    categories['wlasne'].append({
                        'code': code,
                        'name': r.get('opis') or f"Lokalizacja {code}",
                        'zone': "Słownik Lokalizacji",
                        'category': 'Własne Lokalizacje'
                    })
        except Exception:
            pass
        finally:
            conn.close()

        total_count = sum(len(items) for items in categories.values())
        return {
            'categories': categories,
            'total_count': total_count
        }

    @classmethod
    def get_qr_settings(cls) -> Dict[str, Any]:
        """Pobiera aktualne ustawienia etykiet QR z bazy lub zwraca domyślne 80x80 mm."""
        default_settings = {
            'width_mm': cls.DEFAULT_WIDTH_MM,
            'height_mm': cls.DEFAULT_HEIGHT_MM,
            'dpi': cls.DEFAULT_DPI,
            'ecc_level': 'M',
            'show_border': True,
            'show_title': True,
            'company_title': 'MAGAZYN',
            'default_printer': 'Magazyn'
        }
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT wartosc FROM ustawienia WHERE klucz = 'qr_label_settings' LIMIT 1")
            row = cur.fetchone()
            if row and row.get('wartosc'):
                saved = json.loads(row['wartosc'])
                default_settings.update(saved)
        except Exception:
            pass
        finally:
            conn.close()

        return default_settings

    @classmethod
    def save_qr_settings(cls, settings: Dict[str, Any]) -> Tuple[bool, str]:
        """Zapisuje ustawienia etykiet QR w tabeli ustawienia."""
        try:
            width_mm = int(settings.get('width_mm', cls.DEFAULT_WIDTH_MM))
            height_mm = int(settings.get('height_mm', cls.DEFAULT_HEIGHT_MM))
        except (ValueError, TypeError):
            width_mm, height_mm = cls.DEFAULT_WIDTH_MM, cls.DEFAULT_HEIGHT_MM

        payload = {
            'width_mm': max(30, min(width_mm, 200)),
            'height_mm': max(30, min(height_mm, 200)),
            'dpi': int(settings.get('dpi', cls.DEFAULT_DPI)),
            'ecc_level': str(settings.get('ecc_level', 'M')).upper(),
            'show_border': bool(settings.get('show_border', True)),
            'show_title': bool(settings.get('show_title', True)),
            'company_title': str(settings.get('company_title', 'MAGAZYN')).strip(),
            'default_printer': str(settings.get('default_printer', 'Magazyn')).strip()
        }

        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO ustawienia (klucz, wartosc) 
                VALUES ('qr_label_settings', %s)
                ON DUPLICATE KEY UPDATE wartosc = VALUES(wartosc)
            """, (json.dumps(payload),))
            conn.commit()
            return True, "Ustawienia etykiety QR zostały pomyślnie zapisane."
        except Exception as e:
            conn.rollback()
            return False, f"Błąd zapisu ustawień: {str(e)}"
        finally:
            conn.close()

    @classmethod
    def build_location_zpl_80x80(
        cls, 
        location_code: str, 
        location_name: Optional[str] = None, 
        subtitle: Optional[str] = None,
        width_mm: int = 80,
        height_mm: int = 80
    ) -> str:
        """
        Buduje ZPL dla etykiety lokalizacji o wymiarach 80x80 mm (640x640 dots @ 203 DPI).
        Zawiera ramkę, nagłówek strefy, duży czytelny kod lokalizacji oraz wycentrowany kod QR.
        """
        safe_code = str(location_code or '').strip().upper().replace('^', '').replace('~', '')
        safe_name = str(location_name or safe_code).replace('^', '').replace('~', '')
        safe_sub = str(subtitle or 'LOKALIZACJA MAGAZYNOWA').replace('^', '').replace('~', '')

        # Przelicz wymiary na punkty przy 203 DPI (~8 punktów / mm)
        dots_w = int(width_mm * 8)
        dots_h = int(height_mm * 8)

        # Marginesy
        margin = 20
        inner_w = dots_w - (2 * margin)
        inner_h = dots_h - (2 * margin)

        zpl = "^XA\n"
        zpl += "^CI28\n"  # UTF-8
        zpl += f"^PW{dots_w}\n"
        zpl += f"^LL{dots_h}\n"

        # Zewnętrzna elegancka ramka
        zpl += f"^FO{margin},{margin}^GB{inner_w},{inner_h},4^FS\n"

        # Pasek nagłówkowy (podtytuł strefy)
        zpl += f"^FO{margin + 20},{margin + 24}^A0N,26,26^FB{inner_w - 40},1,0,C^FD{safe_sub}^FS\n"
        zpl += f"^FO{margin + 40},{margin + 58}^GB{inner_w - 80},2,2^FS\n"

        # Duży kod QR (współczynnik skali 7-8 dla idealnej proporcji 80x80mm)
        qr_x = (dots_w // 2) - 100
        zpl += f"^FO{qr_x},{margin + 75}^BQN,2,7^FDMA,{safe_code}^FS\n"

        # Duży, pogrubiony napis lokalizacji na dole
        text_y = dots_h - margin - 100
        zpl += f"^FO{margin + 10},{text_y}^A0N,64,64^FB{inner_w - 20},1,0,C^FD{safe_code}^FS\n"

        # Opcjonalny opis pod kodem
        if safe_name and safe_name != safe_code:
            zpl += f"^FO{margin + 10},{text_y + 68}^A0N,22,22^FB{inner_w - 20},1,0,C^FD{safe_name[:40]}^FS\n"

        zpl += "^XZ"
        return zpl

    @classmethod
    def build_custom_qr_zpl_80x80(
        cls, 
        qr_data: str, 
        display_title: Optional[str] = None, 
        display_sub: Optional[str] = None,
        width_mm: int = 80,
        height_mm: int = 80
    ) -> str:
        """
        Buduje uniwersalny ZPL dla dowolnego tekstu / kodu o wymiarach 80x80 mm.
        """
        safe_data = str(qr_data or '').replace('^', '').replace('~', '')
        title_text = str(display_title or safe_data[:24]).replace('^', '').replace('~', '')
        sub_text = str(display_sub or 'KOD QR').replace('^', '').replace('~', '')

        dots_w = int(width_mm * 8)
        dots_h = int(height_mm * 8)
        margin = 20
        inner_w = dots_w - (2 * margin)
        inner_h = dots_h - (2 * margin)

        zpl = "^XA\n"
        zpl += "^CI28\n"
        zpl += f"^PW{dots_w}\n"
        zpl += f"^LL{dots_h}\n"

        zpl += f"^FO{margin},{margin}^GB{inner_w},{inner_h},4^FS\n"
        zpl += f"^FO{margin + 20},{margin + 24}^A0N,26,26^FB{inner_w - 40},1,0,C^FD{sub_text}^FS\n"
        zpl += f"^FO{margin + 40},{margin + 58}^GB{inner_w - 80},2,2^FS\n"

        qr_x = (dots_w // 2) - 100
        zpl += f"^FO{qr_x},{margin + 75}^BQN,2,7^FDMA,{safe_data}^FS\n"

        text_y = dots_h - margin - 85
        zpl += f"^FO{margin + 10},{text_y}^A0N,44,44^FB{inner_w - 20},1,0,C^FD{title_text}^FS\n"

        zpl += "^XZ"
        return zpl
