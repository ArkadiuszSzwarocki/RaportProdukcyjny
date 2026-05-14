import mysql from 'mysql2/promise';
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
dotenv.config({ path: path.join(__dirname, '../.env') });

async function run() {
  const dbConfig = {
    host: process.env.DB_HOST,
    port: parseInt(process.env.DB_PORT || '3306'),
    user: process.env.DB_USER,
    password: process.env.DB_PASSWORD
  };

  const testDb = `mleczna_test_${Date.now()}`;
  const conn = await mysql.createConnection(dbConfig);
  try {
    // Check current user grants
    try {
      const [grants] = await conn.query("SHOW GRANTS FOR CURRENT_USER()");
      console.log('Current grants sample:', grants[0]);
    } catch (gerr) {
      console.log('Could not fetch grants:', gerr.message);
    }

    console.log('Attempting to create test database', testDb);
    let usedDatabase = null;
    try {
      await conn.query(`CREATE DATABASE IF NOT EXISTS \`${testDb}\``);
      await conn.query(`USE \`${testDb}\``);
      usedDatabase = testDb;
      console.log('Created and using test database', testDb);
    } catch (dbCreateErr) {
      console.warn('Create database failed:', dbCreateErr.message);
      // Fallback: use existing configured database (from env)
      usedDatabase = process.env.DB_NAME;
      console.log('Falling back to existing database:', usedDatabase, "- will create temporary tables prefixed with test_");
      await conn.query(`USE \`${usedDatabase}\``);
    }

    const tableName = `test_items_${Date.now()}`;
    console.log('Creating table', tableName, 'in', usedDatabase);
    await conn.query(`
      CREATE TABLE \`${tableName}\` (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(100),
        meta JSON
      ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    `);

    console.log('Inserting rows into', tableName);
    await conn.query(`INSERT INTO \`${tableName}\` (name, meta) VALUES (?, JSON_OBJECT('a', 1)), (?, JSON_ARRAY(1,2,3))`, ['foo', 'bar']);

    console.log('Selecting rows');
    const [rows] = await conn.query(`SELECT id, name, JSON_EXTRACT(meta, "$") as meta FROM \`${tableName}\``);
    console.log('Rows:', rows);

    console.log('Cleaning up: dropping table', tableName);
    await conn.query(`DROP TABLE \`${tableName}\``);

    if (usedDatabase === testDb) {
      console.log('Dropping test database', testDb);
      await conn.query(`DROP DATABASE \`${testDb}\``);
    }

    console.log('Integration test completed successfully.');
  } catch (e) {
    console.error('Integration test failed:', e.message);
  } finally {
    await conn.end();
  }
}

run().catch(e=>{ console.error(e); process.exit(1); });