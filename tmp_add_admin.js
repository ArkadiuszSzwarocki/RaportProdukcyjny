import mysql from 'mysql2/promise';
import bcrypt from 'bcrypt';
import dotenv from 'dotenv';
dotenv.config();

const dbConfig = {
  host: process.env.DB_HOST || '89.229.76.51',
  port: parseInt(process.env.DB_PORT || '3307'),
  user: process.env.DB_USER || 'rootMlecznaDroga',
  password: process.env.DB_PASSWORD || 'Filipinka2025',
  database: process.env.DB_NAME || 'MleczDroga',
  connectTimeout: 15000
};

(async () => {
  const connection = await mysql.createConnection(dbConfig);
  try {
    const username = 'Admin';
    const password = 'Masterkey';
    const hash = await bcrypt.hash(password, 10);
    const userId = 'admin-' + Date.now();

    const [existing] = await connection.query('SELECT id FROM users WHERE username = ?', [username]);
    if (existing.length > 0) {
      console.log(`Użytkownik ${username} już istnieje. Aktualizuję hasło.`);
      await connection.query('UPDATE users SET password = ?, role = ?, role_id = ? WHERE username = ?', [hash, 'admin', 'admin', username]);
    } else {
      console.log(`Tworzę nowego użytkownika: ${username}`);
      await connection.query(
        'INSERT INTO users (id, username, password, role, role_id) VALUES (?, ?, ?, ?, ?)',
        [userId, username, hash, 'admin', 'admin']
      );
    }
    console.log('✅ Sukces!');
  } catch (err) {
    console.error('❌ Błąd:', err.message);
  } finally {
    await connection.end();
  }
})();
