#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Generator kodów QR dla logowania do systemu RaportProdukcyjny.

Użycie:
    python tools/generate_login_qr.py <login> <haslo> [output_file.png]
    
Przykład:
    python tools/generate_login_qr.py pracownik1 haslo123 qr_pracownik1.png
"""

import sys
import json
import qrcode
from pathlib import Path


def generate_login_qr(login, password, output_file='login_qr.png', format_type='json'):
    """
    Generuje kod QR dla logowania.
    
    Args:
        login (str): Nazwa użytkownika
        password (str): Hasło
        output_file (str): Ścieżka do pliku wyjściowego
        format_type (str): Format danych - 'json' lub 'simple'
    
    Returns:
        str: Ścieżka do wygenerowanego pliku
    """
    
    # Wybierz format danych
    if format_type == 'json':
        qr_data = json.dumps({
            'login': login,
            'haslo': password
        })
    else:  # simple format
        qr_data = f'LOGIN:{login}:{password}'
    
    # Utwórz kod QR
    qr = qrcode.QRCode(
        version=1,  # Auto-size
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # High error correction
        box_size=10,
        border=4,
    )
    
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    # Generuj obraz
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Zapisz plik
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)
    
    print(f'✅ Kod QR wygenerowany: {output_path.absolute()}')
    print(f'   Login: {login}')
    print(f'   Format: {format_type}')
    print(f'\n⚠️  UWAGA: Przechowuj ten plik bezpiecznie!')
    print(f'   Zawiera dane logowania w postaci kodu QR.')
    
    return str(output_path)


def generate_bulk_qr_codes(users_file='users.txt', output_dir='qr_codes'):
    """
    Generuje kody QR dla wielu użytkowników z pliku.
    
    Format pliku users.txt (każda linia):
        login:haslo
    
    Args:
        users_file (str): Ścieżka do pliku z użytkownikami
        output_dir (str): Katalog wyjściowy dla kodów QR
    """
    
    users_path = Path(users_file)
    if not users_path.exists():
        print(f'❌ Plik {users_file} nie istnieje!')
        print(f'   Utwórz plik w formacie:')
        print(f'   pracownik1:haslo123')
        print(f'   pracownik2:haslo456')
        return
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    generated = 0
    errors = 0
    
    with users_path.open('r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            parts = line.split(':', 1)
            if len(parts) != 2:
                print(f'⚠️  Pominięto linię {line_num}: nieprawidłowy format')
                errors += 1
                continue
            
            login, password = parts
            login = login.strip()
            password = password.strip()
            
            if not login or not password:
                print(f'⚠️  Pominięto linię {line_num}: puste pole')
                errors += 1
                continue
            
            try:
                output_file = output_path / f'qr_{login}.png'
                generate_login_qr(login, password, str(output_file))
                generated += 1
            except Exception as e:
                print(f'❌ Błąd dla {login}: {e}')
                errors += 1
    
    print(f'\n{"="*60}')
    print(f'Podsumowanie:')
    print(f'  • Wygenerowano: {generated} kodów QR')
    print(f'  • Błędy: {errors}')
    print(f'  • Katalog: {output_path.absolute()}')
    print(f'{"="*60}')


def main():
    """Główna funkcja CLI."""
    
    if len(sys.argv) < 2:
        print('Użycie:')
        print(f'  {sys.argv[0]} <login> <haslo> [output_file.png]')
        print(f'  {sys.argv[0]} --bulk [users_file.txt] [output_dir]')
        print()
        print('Przykłady:')
        print(f'  {sys.argv[0]} pracownik1 haslo123')
        print(f'  {sys.argv[0]} pracownik1 haslo123 qr_pracownik1.png')
        print(f'  {sys.argv[0]} --bulk users.txt qr_codes')
        return
    
    if sys.argv[1] == '--bulk':
        users_file = sys.argv[2] if len(sys.argv) > 2 else 'users.txt'
        output_dir = sys.argv[3] if len(sys.argv) > 3 else 'qr_codes'
        generate_bulk_qr_codes(users_file, output_dir)
    else:
        if len(sys.argv) < 3:
            print('❌ Błąd: Podaj login i hasło')
            print(f'Użycie: {sys.argv[0]} <login> <haslo> [output_file.png]')
            return
        
        login = sys.argv[1]
        password = sys.argv[2]
        output_file = sys.argv[3] if len(sys.argv) > 3 else f'qr_{login}.png'
        
        generate_login_qr(login, password, output_file)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n\n❌ Przerwano przez użytkownika')
    except Exception as e:
        print(f'\n❌ Nieoczekiwany błąd: {e}')
        import traceback
        traceback.print_exc()
