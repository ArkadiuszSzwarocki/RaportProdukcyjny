-- Nested Handling Units: sub-rolls inside a master packaging pallet (magazyn_opakowania)
CREATE TABLE IF NOT EXISTS magazyn_opakowania_rolki (
    id INT AUTO_INCREMENT PRIMARY KEY,
    parent_opakowanie_id INT NOT NULL,
    kod_rolki VARCHAR(64) NOT NULL UNIQUE,
    nr_rolki INT NOT NULL DEFAULT 1,
    ilosc_szt INT NOT NULL,
    waga_kg DECIMAL(10,3) NULL DEFAULT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'NA_PALECIE',
    lp01_opakowanie_id INT NULL DEFAULT NULL,
    zrodlo VARCHAR(32) NOT NULL DEFAULT 'PODZIAL',
    created_by VARCHAR(100) NULL DEFAULT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_mor_parent_status (parent_opakowanie_id, status),
    INDEX idx_mor_lp01_opak (lp01_opakowanie_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
