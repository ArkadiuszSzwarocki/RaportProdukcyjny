import mysql from 'mysql2/promise';
import dotenv from 'dotenv';
import fs from 'fs';

// Load env from database-server/.env if present
const envPath = './database-server/.env';
if (fs.existsSync(envPath)) {
  dotenv.config({ path: envPath });
} else {
  dotenv.config();
}

(async () => {
  const host = process.env.DB_HOST || 'localhost';
  const port = parseInt(process.env.DB_PORT || '3306', 10);
  const user = process.env.DB_USER || 'root';
  const password = process.env.DB_PASSWORD || '';
  const database = process.env.DB_NAME || 'MleczDroga';

  console.log(`Connecting to DB ${user}@${host}:${port}/${database} ...`);

  try {
    const pool = mysql.createPool({ host, port, user, password, database, connectionLimit: 5 });
    const [rows] = await pool.query("SELECT id, nazwa, currentWeight, currentLocation FROM raw_materials LIMIT 200");
    if (!Array.isArray(rows)) {
      console.log('Unexpected result:', rows);
      process.exit(1);
    }

    console.log(`Found ${rows.length} rows (showing up to 200):`);
    for (const r of rows) {
      console.log(JSON.stringify(r));
    }

    await pool.end();
    process.exit(0);
  } catch (err) {
    console.error('Error querying DB:', err.message || err);
    process.exit(2);
  }
})();
