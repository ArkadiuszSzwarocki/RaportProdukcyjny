-- canonical_schema.sql
-- Zintegrowany, kanoniczny schemat (zbiór najważniejszych tabel wykorzystywanych przez aplikację)
-- Uwaga: przed zastosowaniem na produkcji przetestować na kopii bazy

-- deliveries
CREATE TABLE IF NOT EXISTS deliveries (
  id VARCHAR(50) PRIMARY KEY,
  orderRef VARCHAR(100),
  supplier VARCHAR(100),
  deliveryDate DATE,
  status VARCHAR(50),
  items JSON,
  created_by VARCHAR(50),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  requiresLab TINYINT(1) DEFAULT 0,
  warehouseStageCompletedAt DATETIME,
  INDEX idx_status (status),
  INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- system_logs
CREATE TABLE IF NOT EXISTS system_logs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
  level VARCHAR(20),
  message TEXT,
  context VARCHAR(100),
  user VARCHAR(50),
  INDEX idx_timestamp (timestamp),
  INDEX idx_level (level),
  INDEX idx_user (user)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- users
CREATE TABLE IF NOT EXISTS users (
  id VARCHAR(50) PRIMARY KEY,
  username VARCHAR(50) UNIQUE NOT NULL,
  email VARCHAR(100) UNIQUE,
  password VARCHAR(255),
  pin VARCHAR(10),
  role VARCHAR(50),
  role_id VARCHAR(50),
  sub_role_id VARCHAR(50),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  last_login DATETIME,
  is_active TINYINT(1) DEFAULT 1,
  is_temporary_password TINYINT(1) DEFAULT 0,
  INDEX idx_username (username),
  INDEX idx_role_id (role_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- warehouses
CREATE TABLE IF NOT EXISTS warehouses (
  id VARCHAR(50) PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  location VARCHAR(100),
  capacity INT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- warehouseLocation
CREATE TABLE IF NOT EXISTS warehouseLocation (
  id INT AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(50) NOT NULL UNIQUE,
  name VARCHAR(255) NOT NULL,
  type VARCHAR(50) DEFAULT 'zone',
  capacity INT DEFAULT NULL,
  is_locked TINYINT(1) DEFAULT 0,
  is_active TINYINT(1) DEFAULT 1,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- products
CREATE TABLE IF NOT EXISTS products (
  id VARCHAR(50) PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  sku VARCHAR(50) UNIQUE,
  description TEXT,
  category VARCHAR(50),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- raw_materials (palety)
CREATE TABLE IF NOT EXISTS raw_materials (
  id VARCHAR(50) PRIMARY KEY,
  nrPalety VARCHAR(100),
  nazwa VARCHAR(255),
  dataProdukcji DATE,
  dataPrzydatnosci DATE,
  initialWeight DECIMAL(12,3),
  currentWeight DECIMAL(12,3),
  isBlocked TINYINT(1) DEFAULT 0,
  blockReason TEXT,
  currentLocation VARCHAR(100),
  batchNumber VARCHAR(100),
  packageForm VARCHAR(100),
  unit VARCHAR(50),
  labAnalysisNotes TEXT,
  createdAt DATETIME DEFAULT CURRENT_TIMESTAMP,
  updatedAt DATETIME DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- inventory_sessions
CREATE TABLE IF NOT EXISTS inventory_sessions (
  id VARCHAR(50) PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  userId VARCHAR(50),
  user_id VARCHAR(50),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  createdAt DATETIME DEFAULT CURRENT_TIMESTAMP,
  status VARCHAR(50),
  results JSON,
  finalized_at DATETIME DEFAULT NULL,
  finalized_by VARCHAR(50),
  FOREIGN KEY (userId) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- inventory_snapshots
CREATE TABLE IF NOT EXISTS inventory_snapshots (
  id INT AUTO_INCREMENT PRIMARY KEY,
  session_id VARCHAR(50),
  pallet_id VARCHAR(50),
  product_name VARCHAR(255),
  expected_quantity DECIMAL(12,3),
  location_id VARCHAR(50),
  INDEX idx_session (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- inventory_scans
CREATE TABLE IF NOT EXISTS inventory_scans (
  id INT AUTO_INCREMENT PRIMARY KEY,
  session_id VARCHAR(50),
  location_id VARCHAR(50),
  pallet_id VARCHAR(50),
  counted_quantity DECIMAL(12,3),
  scanned_by VARCHAR(50),
  scanned_at DATETIME DEFAULT NULL,
  UNIQUE KEY uniq_scan (session_id, location_id, pallet_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- roles & sub_roles
CREATE TABLE IF NOT EXISTS roles (
  id VARCHAR(50) PRIMARY KEY,
  name VARCHAR(100),
  label VARCHAR(100),
  permissions JSON
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS sub_roles (
  id VARCHAR(50) PRIMARY KEY,
  role_id VARCHAR(50),
  name VARCHAR(100),
  FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- role_permissions & user_permissions
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

-- Koniec canonical schema
