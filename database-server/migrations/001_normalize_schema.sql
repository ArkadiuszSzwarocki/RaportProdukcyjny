-- 001_normalize_schema.sql
-- Migracja: ujednolicenie nazw kolumn i dodanie brakujących pól używanych w kodzie
-- Uruchomić na bazie MySQL 8+

-- Roles: upewnij się, że istnieją kolumny `label` i `permissions`
ALTER TABLE roles
  ADD COLUMN label VARCHAR(100) DEFAULT NULL,
  ADD COLUMN permissions JSON DEFAULT NULL;

-- Jeśli istnieje `name` ale brak `label`, skopiuj wartość
UPDATE roles SET label = name WHERE label IS NULL AND name IS NOT NULL;

-- Sub-roles: upewnij się, że kolumny zgodne
ALTER TABLE sub_roles
  ADD COLUMN role_id VARCHAR(50) DEFAULT NULL;

-- Users: dodaj brakujące warianty snake_case/camelCase i flagi zgodne z kodem
ALTER TABLE users
  ADD COLUMN email VARCHAR(100) DEFAULT NULL,
  ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  ADD COLUMN last_login DATETIME DEFAULT NULL,
  ADD COLUMN is_active TINYINT(1) DEFAULT 1,
  ADD COLUMN is_temporary_password TINYINT(1) DEFAULT 0,
  ADD COLUMN role_id VARCHAR(50) DEFAULT NULL,
  ADD COLUMN sub_role_id VARCHAR(50) DEFAULT NULL;

-- Jeśli istnieje camelCase `createdAt`, zsynchornizuj (nie nadpisuj istniejących wartości)
UPDATE users SET created_at = createdAt WHERE created_at IS NULL AND createdAt IS NOT NULL;

-- Indexy pomocnicze
ALTER TABLE users ADD INDEX idx_role_id (role_id);
ALTER TABLE users ADD INDEX idx_username (username);

-- Inventory sessions: dodać pola używane przez server.js (snake_case)
ALTER TABLE inventory_sessions
  ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  ADD COLUMN created_by VARCHAR(50) DEFAULT NULL,
  ADD COLUMN finalized_at DATETIME DEFAULT NULL,
  ADD COLUMN finalized_by VARCHAR(50) DEFAULT NULL,
  ADD COLUMN status VARCHAR(50) DEFAULT NULL,
  ADD COLUMN results JSON DEFAULT NULL;

-- Wenn jest userId w schemacie, zachowaj; jeśli nie, dodaj role_id-like pole
ALTER TABLE inventory_sessions ADD COLUMN user_id VARCHAR(50) DEFAULT NULL;

-- Inventory snapshots & scans: upewnij się, że mają oczekiwane kolumny
ALTER TABLE inventory_snapshots
  ADD COLUMN session_id VARCHAR(50) DEFAULT NULL,
  ADD COLUMN pallet_id VARCHAR(50) DEFAULT NULL,
  ADD COLUMN product_name VARCHAR(255) DEFAULT NULL,
  ADD COLUMN expected_quantity DECIMAL(12,3) DEFAULT NULL,
  ADD COLUMN location_id VARCHAR(50) DEFAULT NULL;

ALTER TABLE inventory_scans
  ADD COLUMN session_id VARCHAR(50) DEFAULT NULL,
  ADD COLUMN location_id VARCHAR(50) DEFAULT NULL,
  ADD COLUMN pallet_id VARCHAR(50) DEFAULT NULL,
  ADD COLUMN counted_quantity DECIMAL(12,3) DEFAULT NULL,
  ADD COLUMN scanned_by VARCHAR(50) DEFAULT NULL,
  ADD COLUMN scanned_at DATETIME DEFAULT NULL;

-- Raw materials: upewnij się, że pola używane w kodzie istnieją
ALTER TABLE raw_materials
  ADD COLUMN nrPalety VARCHAR(100) DEFAULT NULL,
  ADD COLUMN nazwa VARCHAR(255) DEFAULT NULL,
  ADD COLUMN initialWeight DECIMAL(12,3) DEFAULT NULL,
  ADD COLUMN currentWeight DECIMAL(12,3) DEFAULT NULL,
  ADD COLUMN currentLocation VARCHAR(100) DEFAULT NULL,
  ADD COLUMN batchNumber VARCHAR(100) DEFAULT NULL,
  ADD COLUMN packageForm VARCHAR(100) DEFAULT NULL,
  ADD COLUMN unit VARCHAR(50) DEFAULT NULL,
  ADD COLUMN labAnalysisNotes TEXT DEFAULT NULL;

-- Deliveries: ensure camelCase or snake_case both present for backward compat
ALTER TABLE deliveries
  ADD COLUMN created_at DATETIME DEFAULT NULL,
  ADD COLUMN created_by VARCHAR(50) DEFAULT NULL;

-- warehouseLocation: ensure both created_at and createdAt exist
ALTER TABLE warehouseLocation
  ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

-- Role & user permissions tables (used by API)
CREATE TABLE IF NOT EXISTS role_permissions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  role_id VARCHAR(50) NOT NULL,
  permission VARCHAR(100) NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY unique_role_permission (role_id, permission)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_permissions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(50) NOT NULL,
  permission VARCHAR(100) NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Synchronizacja prostych wartości: skopiuj `role` -> `role_id` jeśli brak role_id
UPDATE users SET role_id = role WHERE role_id IS NULL AND role IS NOT NULL;

-- Wypełnienie label dla roles
UPDATE roles SET label = COALESCE(label, name) WHERE (label IS NULL OR label = '') AND (name IS NOT NULL AND name != '');

-- Zakończenie migracji
SELECT 'MIGRATION 001_NORMALIZE_SCHEMA COMPLETED' AS info;
