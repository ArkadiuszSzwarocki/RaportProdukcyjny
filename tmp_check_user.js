import mysql from 'mysql2/promise';
import dotenv from 'dotenv';
dotenv.config();

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
    const [rows] = await pool.query('SELECT * FROM users WHERE username = ?', ['admin']);
    console.log('FOUND:', JSON.stringify(rows, null, 2));
  }catch(e){
    console.error('ERR', e.message);
    process.exit(2);
  }finally{
    await pool.end();
  }
})();
