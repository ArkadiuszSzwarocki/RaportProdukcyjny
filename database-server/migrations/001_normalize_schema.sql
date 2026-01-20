-- 001_normalize_schema.sql
-- Migracja: ujednolicenie nazw kolumn i dodanie brakujących pól używanych w kodzie
-- Uruchomić na bazie MySQL 8+ (używa ADD COLUMN IF NOT EXISTS)

-- Roles: upewnij się, że istnieją kolumny `label` i `permissions`
ALTER TABLE roles
  ADD COLUMN IF NOT EXISTS label VARCHAR(100) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS permissions JSON DEFAULT NULL;

-- Jeśli istnieje `name` ale brak `label`, skopiuj wartość
UPDATE roles SET label = name WHERE label IS NULL AND name IS NOT NULL;

-- Sub-roles: upewnij się, że kolumny zgodne
ALTER TABLE sub_roles
  ADD COLUMN IF NOT EXISTS role_id VARCHAR(50) DEFAULT NULL;

-- Users: dodaj brakujące warianty snake_case/camelCase i flagi zgodne z kodem
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS email VARCHAR(100) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  ADD COLUMN IF NOT EXISTS last_login DATETIME DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS is_active TINYINT(1) DEFAULT 1,
  ADD COLUMN IF NOT EXISTS is_temporary_password TINYINT(1) DEFAULT 0,
  ADD COLUMN IF NOT EXISTS role_id VARCHAR(50) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS sub_role_id VARCHAR(50) DEFAULT NULL;

-- Jeśli istnieje camelCase `createdAt`, zsynchornizuj (nie nadpisuj istniejących wartości)
UPDATE users SET created_at = createdAt WHERE created_at IS NULL AND createdAt IS NOT NULL;

-- Indexy pomocnicze
ALTER TABLE users ADD INDEX IF NOT EXISTS idx_role_id (role_id);
ALTER TABLE users ADD INDEX IF NOT EXISTS idx_username (username);

-- Inventory sessions: dodać pola używane przez server.js (snake_case)
ALTER TABLE inventory_sessions
  ADD COLUMN IF NOT EXISTS created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  ADD COLUMN IF NOT EXISTS created_by VARCHAR(50) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS finalized_at DATETIME DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS finalized_by VARCHAR(50) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS results JSON DEFAULT NULL;

-- Wenn jest userId w schemacie, zachowaj; jeśli nie, dodaj role_id-like pole
ALTER TABLE inventory_sessions ADD COLUMN IF NOT EXISTS user_id VARCHAR(50) DEFAULT NULL;

-- Inventory snapshots & scans: upewnij się, że mają oczekiwane kolumny
ALTER TABLE inventory_snapshots
  ADD COLUMN IF NOT EXISTS session_id VARCHAR(50) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS pallet_id VARCHAR(50) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS product_name VARCHAR(255) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS expected_quantity DECIMAL(12,3) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS location_id VARCHAR(50) DEFAULT NULL;

ALTER TABLE inventory_scans
  ADD COLUMN IF NOT EXISTS session_id VARCHAR(50) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS location_id VARCHAR(50) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS pallet_id VARCHAR(50) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS counted_quantity DECIMAL(12,3) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS scanned_by VARCHAR(50) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS scanned_at DATETIME DEFAULT NULL;

-- Raw materials: upewnij się, że pola używane w kodzie istnieją
ALTER TABLE raw_materials
  ADD COLUMN IF NOT EXISTS nrPalety VARCHAR(100) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS nazwa VARCHAR(255) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS initialWeight DECIMAL(12,3) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS currentWeight DECIMAL(12,3) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS currentLocation VARCHAR(100) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS batchNumber VARCHAR(100) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS packageForm VARCHAR(100) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS unit VARCHAR(50) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS labAnalysisNotes TEXT DEFAULT NULL;

-- Deliveries: ensure camelCase or snake_case both present for backward compat
ALTER TABLE deliveries
  ADD COLUMN IF NOT EXISTS created_at DATETIME DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS created_by VARCHAR(50) DEFAULT NULL;

-- warehouseLocation: ensure both created_at and createdAt exist
ALTER TABLE warehouseLocation
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  ADD COLUMN IF NOT EXISTS updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

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
