import mysql from 'mysql2/promise';
import dotenv from 'dotenv';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
dotenv.config({ path: path.join(__dirname, '../.env') });

const dbConfig = {
  host: process.env.DB_HOST || 'localhost',
  port: parseInt(process.env.DB_PORT || '3306'),
  user: process.env.DB_USER || 'root',
  password: process.env.DB_PASSWORD || '',
  database: process.env.DB_NAME || undefined,
  multipleStatements: true
};

const ensureColumn = async (conn, table, column, definition) => {
  const [rows] = await conn.query(
    `SELECT COUNT(*) as c FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ? AND COLUMN_NAME = ?`,
    [table, column]
  );
  if (rows[0].c === 0) {
    console.log(`Adding column ${column} to ${table}`);
    await conn.query(`ALTER TABLE \`${table}\` ADD COLUMN ${definition}`);
  } else console.log(`Column ${column} already exists on ${table}`);
};

const ensureIndex = async (conn, table, indexName, expression) => {
  const [rows] = await conn.query(
    `SELECT COUNT(*) as c FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ? AND INDEX_NAME = ?`,
    [table, indexName]
  );
  if (rows[0].c === 0) {
    console.log(`Adding index ${indexName} on ${table}`);
    await conn.query(`ALTER TABLE \`${table}\` ADD INDEX ${indexName} (${expression})`);
  } else console.log(`Index ${indexName} exists on ${table}`);
};

const ensureTable = async (conn, sql) => {
  await conn.query(sql);
};

(async () => {
  const conn = await mysql.createConnection(dbConfig);
  try {
    console.log('DB:', dbConfig.host + ':' + dbConfig.port, 'DBNAME:', dbConfig.database);

    // roles: ensure label and permissions
    await ensureColumn(conn, 'roles', 'label', 'label VARCHAR(100) DEFAULT NULL');
    await ensureColumn(conn, 'roles', 'permissions', 'permissions JSON DEFAULT NULL');

    // if name column exists but label empty, copy
    const [roleNameCol] = await conn.query(`SELECT COUNT(*) as c FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='roles' AND COLUMN_NAME='name'`);
    if (roleNameCol[0].c > 0) {
      console.log('roles.name exists - copying to label where empty');
      await conn.query(`UPDATE roles SET label = name WHERE (label IS NULL OR label = '') AND (name IS NOT NULL AND name != '')`);
    }

    // sub_roles: ensure role_id
    await ensureColumn(conn, 'sub_roles', 'role_id', "role_id VARCHAR(50) DEFAULT NULL");

    // users: defensive columns
    await ensureColumn(conn, 'users', 'email', 'email VARCHAR(100) DEFAULT NULL');
    await ensureColumn(conn, 'users', 'created_at', 'created_at DATETIME DEFAULT CURRENT_TIMESTAMP');
    await ensureColumn(conn, 'users', 'last_login', 'last_login DATETIME DEFAULT NULL');
    await ensureColumn(conn, 'users', 'is_active', 'is_active TINYINT(1) DEFAULT 1');
    await ensureColumn(conn, 'users', 'is_temporary_password', 'is_temporary_password TINYINT(1) DEFAULT 0');
    await ensureColumn(conn, 'users', 'role_id', 'role_id VARCHAR(50) DEFAULT NULL');
    await ensureColumn(conn, 'users', 'sub_role_id', 'sub_role_id VARCHAR(50) DEFAULT NULL');

    // sync createdAt -> created_at when needed
    const [hasCreatedAtCamel] = await conn.query(`SELECT COUNT(*) as c FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='users' AND COLUMN_NAME='createdAt'`);
    if (hasCreatedAtCamel[0].c > 0) {
      console.log('users.createdAt exists, copying to created_at where missing');
      await conn.query(`UPDATE users SET created_at = createdAt WHERE created_at IS NULL AND createdAt IS NOT NULL`);
    }

    await ensureIndex(conn, 'users', 'idx_role_id', 'role_id');
    await ensureIndex(conn, 'users', 'idx_username', 'username');

    // inventory_sessions: ensure snake_case fields used by code
    await ensureColumn(conn, 'inventory_sessions', 'created_at', 'created_at DATETIME DEFAULT CURRENT_TIMESTAMP');
    await ensureColumn(conn, 'inventory_sessions', 'created_by', 'created_by VARCHAR(50) DEFAULT NULL');
    await ensureColumn(conn, 'inventory_sessions', 'finalized_at', 'finalized_at DATETIME DEFAULT NULL');
    await ensureColumn(conn, 'inventory_sessions', 'finalized_by', 'finalized_by VARCHAR(50) DEFAULT NULL');
    await ensureColumn(conn, 'inventory_sessions', 'status', "status VARCHAR(50) DEFAULT NULL");
    await ensureColumn(conn, 'inventory_sessions', 'results', 'results JSON DEFAULT NULL');
    await ensureColumn(conn, 'inventory_sessions', 'user_id', 'user_id VARCHAR(50) DEFAULT NULL');

    // inventory_snapshots / inventory_scans
    await ensureColumn(conn, 'inventory_snapshots', 'session_id', "session_id VARCHAR(50) DEFAULT NULL");
    await ensureColumn(conn, 'inventory_snapshots', 'pallet_id', "pallet_id VARCHAR(50) DEFAULT NULL");
    await ensureColumn(conn, 'inventory_snapshots', 'product_name', "product_name VARCHAR(255) DEFAULT NULL");
    await ensureColumn(conn, 'inventory_snapshots', 'expected_quantity', "expected_quantity DECIMAL(12,3) DEFAULT NULL");
    await ensureColumn(conn, 'inventory_snapshots', 'location_id', "location_id VARCHAR(50) DEFAULT NULL");

    await ensureColumn(conn, 'inventory_scans', 'session_id', "session_id VARCHAR(50) DEFAULT NULL");
    await ensureColumn(conn, 'inventory_scans', 'location_id', "location_id VARCHAR(50) DEFAULT NULL");
    await ensureColumn(conn, 'inventory_scans', 'pallet_id', "pallet_id VARCHAR(50) DEFAULT NULL");
    await ensureColumn(conn, 'inventory_scans', 'counted_quantity', "counted_quantity DECIMAL(12,3) DEFAULT NULL");
    await ensureColumn(conn, 'inventory_scans', 'scanned_by', "scanned_by VARCHAR(50) DEFAULT NULL");
    await ensureColumn(conn, 'inventory_scans', 'scanned_at', "scanned_at DATETIME DEFAULT NULL");

    // raw_materials
    await ensureColumn(conn, 'raw_materials', 'nrPalety', "nrPalety VARCHAR(100) DEFAULT NULL");
    await ensureColumn(conn, 'raw_materials', 'nazwa', "nazwa VARCHAR(255) DEFAULT NULL");
    await ensureColumn(conn, 'raw_materials', 'initialWeight', "initialWeight DECIMAL(12,3) DEFAULT NULL");
    await ensureColumn(conn, 'raw_materials', 'currentWeight', "currentWeight DECIMAL(12,3) DEFAULT NULL");
    await ensureColumn(conn, 'raw_materials', 'currentLocation', "currentLocation VARCHAR(100) DEFAULT NULL");
    await ensureColumn(conn, 'raw_materials', 'batchNumber', "batchNumber VARCHAR(100) DEFAULT NULL");
    await ensureColumn(conn, 'raw_materials', 'packageForm', "packageForm VARCHAR(100) DEFAULT NULL");
    await ensureColumn(conn, 'raw_materials', 'unit', "unit VARCHAR(50) DEFAULT NULL");
    await ensureColumn(conn, 'raw_materials', 'labAnalysisNotes', "labAnalysisNotes TEXT DEFAULT NULL");

    // deliveries
    await ensureColumn(conn, 'deliveries', 'created_at', 'created_at DATETIME DEFAULT NULL');
    await ensureColumn(conn, 'deliveries', 'created_by', 'created_by VARCHAR(50) DEFAULT NULL');

    // warehouseLocation
    await ensureColumn(conn, 'warehouseLocation', 'created_at', 'created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP');
    await ensureColumn(conn, 'warehouseLocation', 'updated_at', 'updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP');

    // Ensure role_permissions and user_permissions tables exist
    await ensureTable(conn, `CREATE TABLE IF NOT EXISTS role_permissions (
      id INT AUTO_INCREMENT PRIMARY KEY,
      role_id VARCHAR(50) NOT NULL,
      permission VARCHAR(100) NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      UNIQUE KEY unique_role_permission (role_id, permission)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;`);

    await ensureTable(conn, `CREATE TABLE IF NOT EXISTS user_permissions (
      id INT AUTO_INCREMENT PRIMARY KEY,
      user_id VARCHAR(50) NOT NULL,
      permission VARCHAR(100) NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;`);

    // sync simple values safely
    const [hasRoleCol] = await conn.query(`SELECT COUNT(*) as c FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='users' AND COLUMN_NAME='role'`);
    const [hasRoleIdCol] = await conn.query(`SELECT COUNT(*) as c FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='users' AND COLUMN_NAME='role_id'`);
    if (hasRoleCol[0].c > 0 && hasRoleIdCol[0].c > 0) {
      console.log('Syncing users.role -> users.role_id where role_id is null');
      await conn.query(`UPDATE users SET role_id = role WHERE role_id IS NULL AND role IS NOT NULL`);
    }

    console.log('Defensive migration completed.');
  } catch (err) {
    console.error('Migration error:', err);
  } finally {
    await conn.end();
  }
})();
