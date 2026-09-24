import mysql from 'mysql2/promise';

const requiredEnv = ['DB_HOST', 'DB_USER', 'DB_PASSWORD', 'DB_NAME'];
const missingEnv = requiredEnv.filter((name) => !process.env[name]);

if (missingEnv.length > 0) {
  throw new Error(`Missing required database environment variables: ${missingEnv.join(', ')}`);
}

const config = {
  host: process.env.DB_HOST,
  port: Number(process.env.DB_PORT || 3306),
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME,
};

(async () => {
  const conn = await mysql.createConnection(config);
  const sql = `
    CREATE TABLE IF NOT EXISTS inventory_snapshots (
      id INT AUTO_INCREMENT PRIMARY KEY,
      session_id VARCHAR(50),
      pallet_id VARCHAR(50),
      product_name VARCHAR(255),
      expected_quantity DECIMAL(10,3),
      location_id VARCHAR(100),
      FOREIGN KEY (session_id) REFERENCES inventory_sessions(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;
  `;

  try {
    const [res] = await conn.query(sql);
    console.log('CREATE TABLE result:', res);
  } catch (err) {
    console.error('Error creating inventory_snapshots:', err);
  } finally {
    await conn.end();
  }
})();
