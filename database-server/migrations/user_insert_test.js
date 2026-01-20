import mysql from 'mysql2/promise';
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';
import bcrypt from 'bcrypt';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
dotenv.config({ path: path.join(__dirname, '../.env') });

const dbConfig = {
  host: process.env.DB_HOST || 'localhost',
  port: parseInt(process.env.DB_PORT || '3306'),
  user: process.env.DB_USER || 'root',
  password: process.env.DB_PASSWORD || '',
  database: process.env.DB_NAME || undefined
};

(async () => {
  const conn = await mysql.createConnection(dbConfig);
  try {
    console.log('Connecting to', dbConfig.host + ':' + dbConfig.port, 'DB:', dbConfig.database);

    const [cols] = await conn.query("SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT, EXTRA, COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='users'");
    console.log('Users table columns:');
    cols.forEach(c => console.log('-', c.COLUMN_NAME, c.DATA_TYPE, c.IS_NULLABLE, c.COLUMN_DEFAULT, c.EXTRA));

    // determine required columns (NOT NULL, no default, not auto_increment)
    const required = cols.filter(c => c.IS_NULLABLE === 'NO' && c.COLUMN_DEFAULT === null && !(c.EXTRA || '').includes('auto_increment')).map(c => c.COLUMN_NAME);
    console.log('Required columns (no default, not nullable, not auto_inc):', required);

    // Build values map
    const values = {};

    // username
    if (cols.some(c => c.COLUMN_NAME === 'username')) values.username = 'test_user_' + Date.now();

    // password / password_hash
    if (cols.some(c => c.COLUMN_NAME === 'password_hash')) {
      const hash = await bcrypt.hash('TempPass123!', 10);
      values.password_hash = hash;
    } else if (cols.some(c => c.COLUMN_NAME === 'password')) {
      const hash = await bcrypt.hash('TempPass123!', 10);
      values.password = hash;
    }

    // role/role_id
    const [rolesRows] = await conn.query('SELECT id FROM roles LIMIT 1');
    if (rolesRows && rolesRows.length > 0) {
      if (cols.some(c => c.COLUMN_NAME === 'role_id')) values.role_id = rolesRows[0].id;
      else if (cols.some(c => c.COLUMN_NAME === 'role')) values.role = rolesRows[0].id;
    } else {
      if (cols.some(c => c.COLUMN_NAME === 'role_id')) values.role_id = 'user';
      else if (cols.some(c => c.COLUMN_NAME === 'role')) values.role = 'user';
    }

    // id handling
    const idCol = cols.find(c => c.COLUMN_NAME === 'id');
    if (idCol) {
      const dtype = (idCol.DATA_TYPE || '').toLowerCase();
      const extra = (idCol.EXTRA || '').toLowerCase();
      if (extra.includes('auto_increment')) {
        // omit id
      } else if (['int','bigint','smallint','mediumint','tinyint'].includes(dtype)) {
        values.id = Math.floor(Date.now() % 1000000000);
      } else {
        values.id = 'test-user-' + Date.now();
      }
    }

    // created_at
    if (cols.some(c => c.COLUMN_NAME === 'created_at')) values.created_at = new Date();
    else if (cols.some(c => c.COLUMN_NAME === 'createdAt')) values.createdAt = new Date();

    console.log('Prepared values for insert:', values);

    // check missing required fields
    const missing = required.filter(r => !(r in values));
    if (missing.length > 0) {
      console.error('Cannot perform safe insert - missing required columns:', missing);
      process.exit(1);
    }

    // build insert
    const keys = Object.keys(values);
    const placeholders = keys.map(() => '?').join(',');
    const sql = `INSERT INTO users (${keys.join(',')}) VALUES (${placeholders})`;
    const params = keys.map(k => values[k]);

    await conn.beginTransaction();
    try {
      const [res] = await conn.query(sql, params);
      console.log('Insert OK (will rollback). Result:', res);
      await conn.rollback();
      console.log('Rollback done.');
    } catch (e) {
      await conn.rollback();
      console.error('Insert failed:', e.message);
    }

  } catch (err) {
    console.error('Error:', err.message || err);
  } finally {
    await conn.end();
  }
})();
