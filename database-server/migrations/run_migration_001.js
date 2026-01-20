import mysql from 'mysql2/promise';
import fs from 'fs';
import path from 'path';
import dotenv from 'dotenv';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
dotenv.config({ path: path.join(__dirname, '../.env') });

(async () => {
    try {
        const sqlPath = path.join(__dirname, '001_normalize_schema.sql');
        if (!fs.existsSync(sqlPath)) {
            console.error('Brak pliku migracji:', sqlPath);
            process.exit(1);
        }
        const sql = fs.readFileSync(sqlPath, 'utf8');

        const conn = await mysql.createConnection({
            host: process.env.DB_HOST || 'localhost',
            port: parseInt(process.env.DB_PORT || '3306'),
            user: process.env.DB_USER || 'root',
            password: process.env.DB_PASSWORD || '',
            database: process.env.DB_NAME || undefined,
            multipleStatements: true
        });

        console.log('Połączenie z', process.env.DB_HOST + ':' + process.env.DB_PORT);
        console.log('Uruchamiam migrację:', sqlPath);
        // Rozbijamy plik SQL na pojedyncze polecenia i wykonujemy sekwencyjnie,
        // ignorując pojedyncze błędy aby migracja mogła kontynuować.
        const statements = sql.split(/;\s*\r?\n/).map(s => s.trim()).filter(Boolean);
        for (const stmt of statements) {
            try {
                const [res] = await conn.query(stmt);
                console.log('OK:', stmt.split('\n')[0].slice(0, 120));
            } catch (e) {
                console.warn('Warn (skipping statement):', e.code || e.message);
            }
        }
        await conn.end();
        console.log('Migracja zakończona.');
    } catch (err) {
        console.error('Błąd podczas migracji:', err);
        process.exit(2);
    }
})();
