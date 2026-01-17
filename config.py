import os

# Klucz do sesji
SECRET_KEY = 'tajnyKluczAgronetzwerk'

# Dane do bazy
DB_CONFIG = {
    'host': '192.168.0.18',      
    'port': 3307,                
    'database': 'biblioteka',    
    'user': 'biblioteka',        
    'password': 'Filipinka2025',
    'charset': 'utf8mb4'
}

# Folder raportów
if not os.path.exists('raporty'):
    os.makedirs('raporty')