-- Migracja: utwórz tabelę wnioski_wolne
CREATE TABLE IF NOT EXISTS wnioski_wolne (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pracownik_id INT NOT NULL,
    typ VARCHAR(50) NOT NULL,
    data_od DATE NOT NULL,
    data_do DATE NOT NULL,
    czas_od TIME NULL,
    czas_do TIME NULL,
    powod TEXT,
    status VARCHAR(20) DEFAULT 'pending',
    zlozono DATETIME DEFAULT CURRENT_TIMESTAMP,
    decyzja_dnia DATETIME NULL,
    lider_id INT NULL,
    FOREIGN KEY (pracownik_id) REFERENCES pracownicy(id) ON DELETE CASCADE
);
