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
  database: process.env.DB_NAME || undefined,
  multipleStatements: true
};

const pairs = [
  { table: 'deliveries', a: 'orderRef', b: 'order_ref', type: 'VARCHAR(100)' },
  { table: 'deliveries', a: 'deliveryDate', b: 'delivery_date', type: 'DATETIME' },
  { table: 'deliveries', a: 'requiresLab', b: 'requires_lab', type: 'TINYINT(1)' },
  { table: 'deliveries', a: 'createdAt', b: 'created_at', type: 'DATETIME' },

  { table: 'users', a: 'createdAt', b: 'created_at', type: 'DATETIME' },
  { table: 'users', a: 'lastLogin', b: 'last_login', type: 'DATETIME' },
  { table: 'users', a: 'role', b: 'role_id', type: 'VARCHAR(50)' },
  { table: 'users', a: 'password', b: 'password_hash', type: 'VARCHAR(255)' },

  { table: 'inventory_sessions', a: 'createdAt', b: 'created_at', type: 'DATETIME' },
  { table: 'inventory_sessions', a: 'createdBy', b: 'created_by', type: 'VARCHAR(50)' },
  { table: 'inventory_snapshots', a: 'sessionId', b: 'session_id', type: 'VARCHAR(50)' },
  { table: 'inventory_snapshots', a: 'productName', b: 'product_name', type: 'VARCHAR(255)' },
  { table: 'inventory_scans', a: 'countedQuantity', b: 'counted_quantity', type: 'DECIMAL(12,3)' },

  { table: 'roles', a: 'name', b: 'label', type: 'VARCHAR(100)' }
];

(async () => {
  const conn = await mysql.createConnection(dbConfig);
  try {
    console.log('Connecting to', dbConfig.host + ':' + dbConfig.port);

    for (const p of pairs) {
      const { table, a, b, type } = p;
      // check existence
      const [[aExists]] = await conn.query("SELECT COUNT(*) as c FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=? AND COLUMN_NAME=?", [table, a]);
      const [[bExists]] = await conn.query("SELECT COUNT(*) as c FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=? AND COLUMN_NAME=?", [table, b]);

      if (aExists.c === 0 && bExists.c === 0) {
        console.log(`Neither ${a} nor ${b} exist on ${table}, skipping.`);
        continue;
      }

      // If one side missing, create it and copy values
      if (aExists.c === 0 && bExists.c === 1) {
        console.log(`Adding column ${a} to ${table} of type ${type} and copying from ${b}`);
        await conn.query(`ALTER TABLE \`${table}\` ADD COLUMN \`${a}\` ${type} NULL`);
        await conn.query(`UPDATE \`${table}\` SET \`${a}\` = \`${b}\` WHERE \`${a}\` IS NULL`);
      } else if (aExists.c === 1 && bExists.c === 0) {
        console.log(`Adding column ${b} to ${table} of type ${type} and copying from ${a}`);
        await conn.query(`ALTER TABLE \`${table}\` ADD COLUMN \`${b}\` ${type} NULL`);
        await conn.query(`UPDATE \`${table}\` SET \`${b}\` = \`${a}\` WHERE \`${b}\` IS NULL`);
      } else {
        console.log(`Both ${a} and ${b} exist on ${table} (or both missing handled), skipping add.`);
      }

      // create triggers to sync on insert/update: before insert and before update
      const trigInsert = `trg_sync_${table}_${a}_${b}_bi`;
      const trigUpdate = `trg_sync_${table}_${a}_${b}_bu`;

      // drop existing triggers if any (to be idempotent)
      try { await conn.query(`DROP TRIGGER IF EXISTS \`${trigInsert}\``); } catch(e) {}
      try { await conn.query(`DROP TRIGGER IF EXISTS \`${trigUpdate}\``); } catch(e) {}

      const insertBody = `
        IF NEW.${a} IS NULL OR NEW.${a} = '' THEN
          SET NEW.${a} = NEW.${b};
        END IF;
        IF NEW.${b} IS NULL OR NEW.${b} = '' THEN
          SET NEW.${b} = NEW.${a};
        END IF;
      `;

      const updateBody = insertBody; // same logic

      // Build create trigger statements
      const createInsertTrigger = `CREATE TRIGGER \`${trigInsert}\` BEFORE INSERT ON \`${table}\` FOR EACH ROW BEGIN ${insertBody} END`;
      const createUpdateTrigger = `CREATE TRIGGER \`${trigUpdate}\` BEFORE UPDATE ON \`${table}\` FOR EACH ROW BEGIN ${updateBody} END`;

      try {
        await conn.query(createInsertTrigger);
        await conn.query(createUpdateTrigger);
        console.log(`Triggers created for ${table}: ${trigInsert}, ${trigUpdate}`);
      } catch (e) {
        console.warn('Could not create triggers for', table, e.message);
      }
    }

    console.log('Alias sync migration completed.');
  } catch (err) {
    console.error('Migration error:', err.message || err);
  } finally {
    await conn.end();
  }
})();
