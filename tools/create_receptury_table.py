import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("USE biblioteka")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS receptury_agro_skladniki (
        id              INT AUTO_INCREMENT PRIMARY KEY,
        nr_receptury    VARCHAR(64) NOT NULL,
        nazwa_produktu  VARCHAR(100) NOT NULL,
        kolejnosc       INT DEFAULT 0,
        skladnik_nazwa  VARCHAR(255) NOT NULL,
        ilosc_kg_szarza FLOAT NULL DEFAULT NULL,
        typ             VARCHAR(50) DEFAULT 'surowiec',
        aktywny         TINYINT(1) DEFAULT 1,
        created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_receptury_agro_nr (nr_receptury),
        INDEX idx_receptury_agro_aktywny (aktywny)
    )
""")
conn.commit()
print("Tabela stworzona (lub już istnieje)")
cursor.execute("DESCRIBE receptury_agro_skladniki")
for r in cursor.fetchall():
    print(r)
cursor.close()
conn.close()
