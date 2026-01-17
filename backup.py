import shutil
import os
from datetime import datetime

def wykonaj_backup():
    # Co kopiujemy?
    zrodlo = 'raporty'
    # Gdzie zapisujemy? (Folder 'backups' w głównym katalogu)
    cel_folder = 'backups'
    
    # Upewnij się, że jest co kopiować
    if not os.path.exists(zrodlo):
        print("⚠️  Brak folderu 'raporty' - pomijam backup.")
        return

    # Stwórz folder na kopie, jeśli nie istnieje
    if not os.path.exists(cel_folder):
        os.makedirs(cel_folder)
    
    # Nazwa pliku z datą i godziną (np. backup_raporty_2023-10-27_06-30.zip)
    nazwa_pliku = f"backup_raporty_{datetime.now().strftime('%Y-%m-%d_%H-%M')}"
    sciezka_pelna = os.path.join(cel_folder, nazwa_pliku)
    
    try:
        # Tworzenie ZIPa
        shutil.make_archive(sciezka_pelna, 'zip', zrodlo)
        print(f"✅ KOPIA ZAPASOWA GOTOWA: {nazwa_pliku}.zip")
        
        # Opcjonalnie: Usuwanie starych kopii (starszych niż 30 dni)
        # To zapobiegnie zapchaniu dysku
        teraz = datetime.now().timestamp()
        for f in os.listdir(cel_folder):
            f_path = os.path.join(cel_folder, f)
            if os.path.isfile(f_path):
                # Jeśli plik starszy niż 30 dni (30 * 24 * 3600 sekund)
                if teraz - os.path.getmtime(f_path) > 30 * 86400:
                    os.remove(f_path)
                    print(f"🗑 Usunięto starą kopię: {f}")
                    
    except Exception as e:
        print(f"❌ Błąd backupu: {e}")

if __name__ == "__main__":
    wykonaj_backup()