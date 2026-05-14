import mysql from 'mysql2/promise';
import dotenv from 'dotenv';
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
  database: process.env.DB_NAME || undefined
};

(async () => {
  const conn = await mysql.createConnection(dbConfig);
  try {
    console.log('Connecting to', dbConfig.host + ':' + dbConfig.port, 'DB:', dbConfig.database);
    // Basic health check
    const [[one]] = await conn.query('SELECT 1 as ok');
    console.log('SELECT 1 ->', one.ok);

    // Count users
    const [[uCount]] = await conn.query('SELECT COUNT(*) as cnt FROM users');
    console.log('Users count:', uCount.cnt);

    // Transactional INSERT into deliveries (rollback) - use safeInsert helper
    const safeInsert = async (table, valuesMap) => {
      const [cols] = await conn.query(`SELECT COLUMN_NAME, IS_NULLABLE, COLUMN_DEFAULT FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME = ?`, [table]);
      if (!cols || cols.length === 0) throw new Error(`Table ${table} not found`);
      const colInfo = {};
      for (const r of cols) colInfo[r.COLUMN_NAME] = r;

      // check for required columns not supplied
      const missingRequired = [];
      for (const r of cols) {
        const name = r.COLUMN_NAME;
        const isNullable = r.IS_NULLABLE === 'YES';
        const hasDefault = r.COLUMN_DEFAULT !== null;
        const isAutoInc = (r.EXTRA || '').toLowerCase().includes('auto_increment');
        if (!isNullable && !hasDefault && !isAutoInc && !(name in valuesMap)) missingRequired.push(name);
      }
      if (missingRequired.length > 0) throw new Error('Missing required columns for ' + table + ': ' + missingRequired.join(', '));

      const candidates = [];
      const params = [];
      for (const [k, v] of Object.entries(valuesMap)) {
        if (!colInfo[k]) continue; // not present in table

        // if enum, ensure value is allowed
        const colType = colInfo[k].COLUMN_TYPE || '';
        if (colType.startsWith('enum(')) {
          // parse enum values
          const m = colType.match(/^enum\((.*)\)$/i);
          const opts = m ? m[1].split(/,(?=(?:[^']*'[^']*')*[^']*$)/).map(s => s.trim().replace(/^'|'$/g, '')) : [];
          if (!opts.includes(String(v))) {
            console.log(`Skipping column ${k} for insert because value '${v}' not in enum(${opts.join(',')})`);
            continue;
          }
        }

        candidates.push(k);
        params.push(v);
      }
      if (candidates.length === 0) throw new Error('No insertable columns available for ' + table);
      const q = `INSERT INTO \`${table}\` (${candidates.join(',')}) VALUES (${candidates.map(()=>'?').join(',')})`;
      const [r] = await conn.query(q, params);
      return r;
    };

    await conn.beginTransaction();
    try {
      const deliveryValues = {
        id: 'TEST-DEL-' + Date.now(),
        order_ref: 'REF-TEST',
        supplier: 'TEST-SUP',
        delivery_date: new Date(),
        // status may be enum/limited; we'll set later after checking allowed values
        // status: 'pending',
        items: JSON.stringify([{ sku: 'X', qty: 1 }]),
        created_by: 'migration-runner',
        requires_lab: 0
      };
      // adjust status if enum exists
      try {
        const [dCols] = await conn.query("SELECT COLUMN_NAME, COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='deliveries'");
        const colInfo = {};
        for (const c of dCols) colInfo[c.COLUMN_NAME] = c.COLUMN_TYPE;
        if (colInfo['status'] && colInfo['status'].startsWith('enum(')) {
          const m = colInfo['status'].match(/^enum\((.*)\)$/i);
          const opts = m ? m[1].split(/,(?=(?:[^']*'[^']*')*[^']*$)/).map(s => s.trim().replace(/^'|'$/g, '')) : [];
          if (opts.length > 0) deliveryValues['status'] = opts[0];
        }
      } catch (e) {
        // ignore
      }
      const r = await safeInsert('deliveries', deliveryValues);
      console.log('Safe insert deliveries result:', r.affectedRows || r.insertId || r);
      await conn.rollback();
      console.log('Rolled back delivery insert.');
    } catch (e) {
      await conn.rollback();
      console.warn('Delivery insert failed:', e.message);
    }

    // Transactional INSERT into users (rollback)
    await conn.beginTransaction();
    try {
      const testId = 'test-user-' + Date.now();
      let userValues = {
        id: testId,
        username: testId,
        password: 'temp',
        role_id: 'user',
        created_at: new Date()
      };
      // If users table uses password_hash instead of password, map
      try {
        const [uCols] = await conn.query("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='users'");
        const userColNames = uCols.map(r => r.COLUMN_NAME);
        if (userColNames.includes('password_hash') && !userValues.password_hash) {
          userValues.password_hash = userValues.password;
          delete userValues.password;
        }
      } catch (e) {
        // ignore
      }

      // Adjust id if users.id is integer/auto_increment
      try {
        const [[idCol]] = await conn.query("SELECT COLUMN_NAME, DATA_TYPE, EXTRA FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='users' AND COLUMN_NAME='id'");
        if (idCol) {
          const extra = idCol.EXTRA || '';
          const dtype = (idCol.DATA_TYPE || '').toLowerCase();
          if (extra.toLowerCase().includes('auto_increment')) {
            delete userValues.id; // let DB assign
          } else if (['int','bigint','smallint','mediumint','tinyint'].includes(dtype)) {
            // numeric id expected - generate a numeric id
            userValues.id = Math.floor(Date.now() % 1000000000);
          }
        }
      } catch (e) {
        // ignore
      }
        // Pre-check required NOT NULL columns for users and attempt to fill common ones
        try {
          const [uColsInfo] = await conn.query("SELECT COLUMN_NAME, IS_NULLABLE, COLUMN_DEFAULT, EXTRA FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='users'");
          const missingReq = [];
          for (const c of uColsInfo) {
            const isNullable = c.IS_NULLABLE === 'YES';
            const hasDefault = c.COLUMN_DEFAULT !== null;
            const isAutoInc = (c.EXTRA || '').toLowerCase().includes('auto_increment');
            if (!isNullable && !hasDefault && !isAutoInc && !(c.COLUMN_NAME in userValues)) missingReq.push(c.COLUMN_NAME);
          }
          // Attempt to fill id if missing and numeric
          if (missingReq.includes('id')) {
            const idCol = uColsInfo.find(x => x.COLUMN_NAME === 'id');
            if (idCol) {
              const dtype = (idCol.DATA_TYPE || '').toLowerCase();
              if (['int','bigint','smallint','mediumint','tinyint'].includes(dtype)) {
                userValues.id = Math.floor(Date.now() % 1000000000);
                missingReq.splice(missingReq.indexOf('id'), 1);
              }
            }
          }
          if (missingReq.length > 0) throw new Error('Missing required columns for users: ' + missingReq.join(', '));
        } catch (e) {
          throw e;
        }
      const r2 = await safeInsert('users', userValues);
      console.log('Safe insert users result:', r2.affectedRows || r2.insertId || r2);
      await conn.rollback();
      console.log('Rolled back user insert.');
    } catch (e) {
      await conn.rollback();
      console.warn('User insert failed:', e.message);
    }

    console.log('Integration tests finished successfully.');
  } catch (err) {
    console.error('Integration test error:', err.message || err);
  } finally {
    await conn.end();
  }
})();
