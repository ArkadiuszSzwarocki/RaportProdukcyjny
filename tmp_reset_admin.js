import mysql from 'mysql2/promise';
import bcrypt from 'bcrypt';
import dotenv from 'dotenv';
dotenv.config();

const NEW_PASSWORD = process.env.ADMIN_NEW_PASSWORD || 'password';
const dbConfig = {
  host: process.env.DB_HOST || 'filipinka.myqnapcloud.com',
  port: parseInt(process.env.DB_PORT || '3307'),
  user: process.env.DB_USER || 'root',
  password: process.env.DB_PASSWORD || 'Filipinka2010',
  database: process.env.DB_NAME || 'MleczDroga'
};

(async ()=>{
  const pool = await mysql.createPool(dbConfig);
  try{
    const hash = await bcrypt.hash(NEW_PASSWORD, 10);
    const [res] = await pool.query('UPDATE users SET password_hash = ?, is_temporary_password = 1, password_last_changed = NOW() WHERE username = ?', [hash, 'admin']);
    console.log('Updated:', res.affectedRows);
    console.log('New password for admin:', NEW_PASSWORD);
  }catch(e){
    console.error('ERR', e.message);
    process.exit(2);
  }finally{
    await pool.end();
  }
})();
