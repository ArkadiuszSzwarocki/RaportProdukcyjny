CREATE TABLE IF NOT EXISTS agro_workowanie_bigbagi (
    id INT AUTO_INCREMENT PRIMARY KEY,
    plan_id INT NOT NULL,
    paleta_id INT NULL,
    nr_palety VARCHAR(100) NOT NULL,
    nazwa_produktu VARCHAR(255) NOT NULL,
    waga_kg DECIMAL(10,2) NOT NULL,
    nr_partii VARCHAR(100) NULL,
    data_produkcji VARCHAR(50) NULL,
    data_przydatnosci VARCHAR(50) NULL,
    typ_palety VARCHAR(50) DEFAULT 'Surowiec',
    lokalizacja_zrodlowa VARCHAR(50) NULL,
    stan_magazynowy_przed DECIMAL(10,2) NULL,
    autor_login VARCHAR(100) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) DEFAULT 'ZUZYTY',
    INDEX idx_plan_id (plan_id),
    INDEX idx_nr_palety (nr_palety)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
