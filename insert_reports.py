from app.db import get_db_connection

def insert():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT IGNORE INTO przypisania_raportow (typ_raportu, nazwa_raportu, nazwa_drukarki, aktywne) VALUES ('raport_palet_psd', 'Raport Palet (Zakończenie Zlecenia PSD)', 'Brother DCP-T525W Printer', 1)")
    c.execute("INSERT IGNORE INTO przypisania_raportow (typ_raportu, nazwa_raportu, nazwa_drukarki, aktywne) VALUES ('raport_dostawy_zewnetrznej', 'Raport Dostawy Zewnętrznej', 'Brother DCP-T525W Printer', 1)")
    c.execute("INSERT IGNORE INTO przypisania_raportow (typ_raportu, nazwa_raportu, nazwa_drukarki, aktywne) VALUES ('raport_zasypy_dosypki', 'Raport Zasypów i Dosypek', 'Brother DCP-T525W Printer', 1)")
    conn.commit()
    conn.close()
    print("Done")

if __name__ == '__main__':
    insert()
