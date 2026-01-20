-- Schema dla bazy danych Mleczna Droga (MySQL)
-- Host: filipinka.myqnapcloud.com:3307
-- Baza: MleczDroga
-- NOTE: This file uses MySQL-specific syntax (IF NOT EXISTS, COMMENT, JSON column type, ENGINE=InnoDB, etc.).
-- If you need Microsoft SQL Server (T-SQL) compatible statements, see `schema_mssql.sql` in the same folder.
-- Keep this file for MySQL deployments; use schema_mssql.sql for MS SQL deployments.

-- =====================================================
-- Tabela dostaw (Deliveries)
-- =====================================================
CREATE TABLE IF NOT EXISTS deliveries (
    id VARCHAR(50) PRIMARY KEY COMMENT 'Unikalny identyfikator dostawy',
    orderRef VARCHAR(100) COMMENT 'Numer zamówienia',
    supplier VARCHAR(100) COMMENT 'Dostawca',
    deliveryDate DATE COMMENT 'Data dostawy',
    status VARCHAR(50) COMMENT 'Status dostawy (pending, received, processed, etc)',
    items JSON COMMENT 'Szczegóły towarów w JSON',
    createdBy VARCHAR(50) COMMENT 'Użytkownik, który utworzył dostawę',
    createdAt DATETIME COMMENT 'Data i czas utworzenia rekordu',
    requiresLab TINYINT(1) DEFAULT 0 COMMENT 'Czy wymaga badań laboratoryjnych',
    warehouseStageCompletedAt DATETIME COMMENT 'Data i czas ukończenia etapu magazynu',
    INDEX idx_status (status),
    INDEX idx_createdAt (createdAt),
    INDEX idx_supplier (supplier)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

-- =====================================================
-- Tabela logów systemowych
-- =====================================================
CREATE TABLE IF NOT EXISTS system_logs (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'Unikalny identyfikator loga',
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT 'Data i czas zdarzenia',
    level VARCHAR(20) COMMENT 'Poziom logowania (INFO, WARNING, ERROR, DEBUG)',
    message TEXT COMMENT 'Wiadomość logowania',
    context VARCHAR(100) COMMENT 'Kontekst (moduł, funkcja)',
    user VARCHAR(50) COMMENT 'Użytkownik, który spowodował zdarzenie',
    INDEX idx_timestamp (timestamp),
    INDEX idx_level (level),
    INDEX idx_user (user)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

-- =====================================================
-- Tabela użytkowników
-- =====================================================
-- =====================================================
-- Tabela użytkowników (ZAKTUALIZOWANA)
-- =====================================================
DROP TABLE IF EXISTS users;
CREATE TABLE users (
    id VARCHAR(50) PRIMARY KEY COMMENT 'Unikalny identyfikator użytkownika',
    username VARCHAR(50) UNIQUE NOT NULL COMMENT 'Nazwa użytkownika',
    email VARCHAR(100) UNIQUE COMMENT 'Adres email',
    password VARCHAR(255) COMMENT 'Hash hasła (bcrypt)',
    pin VARCHAR(10) COMMENT 'PIN do szybkiego logowania',
    role VARCHAR(50) COMMENT 'Nazwa roli (np. admin, magazynier)',
    role_id VARCHAR(50) COMMENT 'ID roli (do powiązań)',
    sub_role_id VARCHAR(50) COMMENT 'ID pod-roli / oddziału',
    createdAt DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT 'Data utworzenia konta',
    lastLogin DATETIME COMMENT 'Ostatnia sesja logowania',
    isActive TINYINT(1) DEFAULT 1 COMMENT 'Czy konto jest aktywne',
    is_temporary_password TINYINT(1) DEFAULT 0 COMMENT 'Wymuszona zmiana hasła',
    INDEX idx_username (username),
    INDEX idx_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Dodanie domyślnego admina (Hasło: admin123 - musisz je zahasować lub użyć skryptu rejestracji)
-- Poniżej przykładowy insert, hasło to bcrypt dla 'admin123'
INSERT INTO users (id, username, role, password, isActive) 
VALUES ('1', 'admin', 'admin', '$2b$10$P2/1d/1d1d1d1d1d1d1d1eExampleHashPlaceholder', 1);

-- =====================================================
-- Tabela magazynów
-- =====================================================
CREATE TABLE IF NOT EXISTS warehouses (
    id VARCHAR(50) PRIMARY KEY COMMENT 'Unikalny identyfikator magazynu',
    name VARCHAR(100) NOT NULL COMMENT 'Nazwa magazynu',
    location VARCHAR(100) COMMENT 'Lokalizacja',
    capacity INT COMMENT 'Pojemność magazynu',
    createdAt DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT 'Data utworzenia',
    INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

-- =====================================================
-- Tabela lokalizacji magazynowych (warehouseLocation)
-- =====================================================
CREATE TABLE IF NOT EXISTS warehouseLocation (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(50) NOT NULL UNIQUE COMMENT 'Kod lokalizacji (np. BF_MS01, R01)',
    name VARCHAR(255) NOT NULL COMMENT 'Nazwa wyświetlana lokalizacji',
    type VARCHAR(50) DEFAULT 'zone' COMMENT 'Typ lokalizacji (warehouse/zone/rack/bin)',
    capacity INT DEFAULT NULL COMMENT 'Pojemność w paletach',
    is_locked TINYINT(1) DEFAULT 0 COMMENT 'Czy lokalizacja zablokowana',
    is_active TINYINT(1) DEFAULT 1 COMMENT 'Czy aktywna (soft-delete)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_code (code),
    INDEX idx_type (type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

-- =====================================================
-- Tabela produktów
-- =====================================================
CREATE TABLE IF NOT EXISTS products (
    id VARCHAR(50) PRIMARY KEY COMMENT 'Unikalny identyfikator produktu',
    name VARCHAR(100) NOT NULL COMMENT 'Nazwa produktu',
    sku VARCHAR(50) UNIQUE COMMENT 'Kod SKU',
    description TEXT COMMENT 'Opis produktu',
    category VARCHAR(50) COMMENT 'Kategoria',
    createdAt DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT 'Data utworzenia',
    INDEX idx_sku (sku),
    INDEX idx_category (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

-- =====================================================
-- Tabela sesji inwentaryzacyjnych
-- =====================================================
CREATE TABLE IF NOT EXISTS inventory_sessions (
    id VARCHAR(50) PRIMARY KEY COMMENT 'Unikalny identyfikator sesji inwentaryzacyjnej',
    name VARCHAR(100) NOT NULL COMMENT 'Nazwa sesji',
    userId VARCHAR(50) NOT NULL COMMENT 'Identyfikator użytkownika',
    createdAt DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT 'Data utworzenia sesji',
    status VARCHAR(50) COMMENT 'Status sesji (ongoing, completed, cancelled)',
    results JSON COMMENT 'Wyniki inwentaryzacji w formacie JSON',
    FOREIGN KEY (userId) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;
