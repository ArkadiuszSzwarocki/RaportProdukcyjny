import express from 'express';
import mysql from 'mysql2/promise';
import cors from 'cors';
import dotenv from 'dotenv';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import bcrypt from 'bcrypt';
import jwt from 'jsonwebtoken';
import multer from 'multer';
import pdfParse from 'pdf-parse';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

dotenv.config();

const app = express();
// Używamy portu 8089 dla uniknięcia konfliktów na QNAP
const PORT = process.env.PORT || 8089;
const JWT_SECRET = process.env.JWT_SECRET || 'your-secret-key-change-in-production-2024';

// Middleware
app.use(cors({ origin: '*' }));
app.options('*', cors());
app.use(express.json());
app.use(express.text({ type: ['text/*', 'application/csv'] }));

const upload = multer({ storage: multer.memoryStorage() });

// Helpers: konwersja snake_case -> camelCase
const toCamel = (s) => s.replace(/_([a-z])/g, (_, c) => c.toUpperCase());
const normalizeRow = (row) => {
    const out = {};
    for (const k of Object.keys(row || {})) out[toCamel(k)] = row[k];
    return out;
};
const normalizeRows = (rows) => (Array.isArray(rows) ? rows.map(normalizeRow) : rows);

// Mapowanie aliasów lokalizacji (z database-server)
const LOCATION_ALIAS_MAP = {
    'BUFFER_MS01': 'BF_MS01', 'BUFFER_MP01': 'BF_MP01', 'BUFFER_MS': 'BF_MS01',
    'BUFFOR_MS01': 'BF_MS01', 'BUFOR_MS01': 'BF_MS01', 'BUFFER_MP': 'BF_MP01',
    'MOP01': 'MOP01', 'PSD': 'PSD'
};
const normalizeLocation = (loc) => {
    if (!loc) return loc;
    const key = String(loc).trim().toUpperCase();
    return LOCATION_ALIAS_MAP[key] || loc;
};

// Konfiguracja Bazy Danych
const dbConfig = {
    host: process.env.DB_HOST || '127.0.0.1',
    port: parseInt(process.env.DB_PORT || '3307'),
    user: process.env.DB_USER,
    password: process.env.DB_PASSWORD,
    database: process.env.DB_NAME,
    waitForConnections: true,
    connectionLimit: 10,
    queueLimit: 0
};

let pool = mysql.createPool(dbConfig);

// Middleware weryfikacji tokena
const verifyToken = (req, res, next) => {
    const token = req.headers['authorization']?.split(' ')[1];
    if (!token) return res.status(401).json({ error: 'Brak tokenu autoryzacji' });
    try {
        const decoded = jwt.verify(token, JWT_SECRET);
        req.userId = decoded.id;
        req.userRole = decoded.role;
        next();
    } catch (err) {
        return res.status(401).json({ error: 'Nieważny token' });
    }
};

// --- Inicjalizacja Tabel ---
async function initTables() {
    try {
        const tableOptions = "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci";
        await pool.execute(`CREATE TABLE IF NOT EXISTS roles (id VARCHAR(50) PRIMARY KEY, name VARCHAR(100) NOT NULL, label VARCHAR(100), permissions JSON) ${tableOptions};`);
        await pool.execute(`CREATE TABLE IF NOT EXISTS sub_roles (id VARCHAR(50) PRIMARY KEY, role_id VARCHAR(50), name VARCHAR(100) NOT NULL, FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE) ${tableOptions};`);
        
        // Nowa tabela dla zleceń produkcyjnych
        await pool.execute(`CREATE TABLE IF NOT EXISTS production_runs (
            id VARCHAR(50) PRIMARY KEY,
            recipe_id VARCHAR(50),
            recipe_name VARCHAR(255),
            target_batch_size_kg DECIMAL(12,3),
            actual_produced_quantity_kg DECIMAL(12,3),
            planned_date VARCHAR(50),
            status VARCHAR(50),
            start_time DATETIME,
            end_time DATETIME,
            created_by VARCHAR(50),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            notes TEXT,
            has_shortages TINYINT(1) DEFAULT 0,
            shelf_life_months INT,
            batches JSON,
            actual_ingredients_used JSON,
            planned_ingredients JSON,
            events JSON,
            samples JSON,
            suggested_transfer_pallets JSON,
            downtimes JSON
        ) ${tableOptions};`);
        
        // --- Poprawka schematu (Dodaj brakujące kolumny jeśli tabela już istniała) ---
        try {
            const [columns] = await pool.query('SHOW COLUMNS FROM production_runs');
            const colNames = columns.map(c => c.Field);
            if (!colNames.includes('planned_date')) {
                console.log('🏗️ Dodaję brakującą kolumnę planned_date...');
                await pool.execute('ALTER TABLE production_runs ADD COLUMN planned_date VARCHAR(50) AFTER actual_produced_quantity_kg');
            }
            if (!colNames.includes('shelf_life_months')) {
                console.log('🏗️ Dodaję brakującą kolumnę shelf_life_months...');
                await pool.execute('ALTER TABLE production_runs ADD COLUMN shelf_life_months INT AFTER has_shortages');
            }
            if (!colNames.includes('downtimes')) {
                console.log('🏗️ Dodaję brakującą kolumnę downtimes...');
                await pool.execute('ALTER TABLE production_runs ADD COLUMN downtimes JSON AFTER suggested_transfer_pallets');
            }
        } catch (e) {
            console.error('⚠️ Nie udało się zaktualizować schematu production_runs:', e.message);
        }
        
        const [roles] = await pool.query('SELECT * FROM roles');
        if (roles.length === 0) {
            await pool.execute(`INSERT INTO roles (id, name, label, permissions) VALUES 
                ('admin', 'Administrator', 'Administrator', '["ALL"]'),
                ('magazynier', 'Magazynier', 'Magazynier', '["VIEW_WAREHOUSE", "SCAN_PALLETS"]'),
                ('planista', 'Planista', 'Planista', '["PLAN_PRODUCTION"]'),
                ('operator', 'Operator', 'Operator', '["VIEW_PRODUCTION"]')
            `);
        }
        console.log('✅ Baza danych i tabele gotowe.');
    } catch (err) {
        console.error('❌ Błąd inicjalizacji tabel:', err.message);
    }
}
initTables();

// ==========================================================
// ENDPOINTY AUTORYZACJI I UŻYTKOWNIKÓW
// ==========================================================

app.post('/api/auth/login', async (req, res) => {
    const { username, password } = req.body;
    if (!username || !password) return res.status(400).json({ error: 'Wymagane dane.' });

    try {
        const [rows] = await pool.query('SELECT * FROM users WHERE username = ?', [username]);
        if (rows.length === 0) return res.status(401).json({ error: 'Błędne dane logowania.' });

        const user = rows[0];
        const hashCandidate = user.password || user.password_hash || null;
        let passwordIsValid = false;

        if (hashCandidate && (hashCandidate.startsWith('$2b$') || hashCandidate.startsWith('$2a$'))) {
            passwordIsValid = await bcrypt.compare(password, hashCandidate);
        } else {
            passwordIsValid = (password === hashCandidate);
        }

        if (!passwordIsValid) return res.status(401).json({ error: 'Błędne dane logowania.' });

        const role = user.role_id || user.role || 'user';
        const token = jwt.sign({ id: user.id, username: user.username, role }, JWT_SECRET, { expiresIn: '24h' });

        const userOut = normalizeRow(user);
        delete userOut.password;
        res.json({ token, user: userOut });
    } catch (err) {
        res.status(500).json({ error: 'Błąd serwera.' });
    }
});

app.get('/api/users', verifyToken, async (req, res) => {
    try {
        const [rows] = await pool.query('SELECT id, username, email, role, sub_role, isActive FROM users ORDER BY username');
        res.json(normalizeRows(rows));
    } catch (err) {
        res.status(500).json({ error: 'Błąd pobierania użytkowników' });
    }
});

// ==========================================================
// ENDPOINTY ZLECEŃ PRODUKCYJNYCH (AGRO)
// ==========================================================

app.get('/api/production-runs', verifyToken, async (req, res) => {
    try {
        const [rows] = await pool.query('SELECT * FROM production_runs ORDER BY planned_date DESC, created_at DESC');
        res.json(normalizeRows(rows));
    } catch (err) {
        console.error('Error fetching production runs:', err);
        res.status(500).json({ error: 'Błąd pobierania zleceń produkcyjnych' });
    }
});

app.post('/api/production-runs', verifyToken, async (req, res) => {
    const run = req.body;
    if (!run.id || !run.recipeId) return res.status(400).json({ error: 'Brak wymaganych danych zlecenia.' });

    try {
        // Przygotuj dane do zapisu (mapowanie camelCase -> snake_case)
        const runData = {
            id: run.id,
            recipe_id: run.recipeId,
            recipe_name: run.recipeName,
            target_batch_size_kg: run.targetBatchSizeKg,
            actual_produced_quantity_kg: run.actualProducedQuantityKg || 0,
            planned_date: run.plannedDate,
            status: run.status || 'planned',
            start_time: run.startTime || null,
            end_time: run.endTime || null,
            created_by: run.createdBy || req.userId || 'system',
            notes: run.notes || '',
            has_shortages: run.hasShortages ? 1 : 0,
            shelf_life_months: run.shelfLifeMonths || 0,
            batches: JSON.stringify(run.batches || []),
            actual_ingredients_used: JSON.stringify(run.actualIngredientsUsed || []),
            planned_ingredients: JSON.stringify(run.plannedIngredients || []),
            events: JSON.stringify(run.events || []),
            samples: JSON.stringify(run.samples || []),
            suggested_transfer_pallets: JSON.stringify(run.suggestedTransferPallets || []),
            downtimes: JSON.stringify(run.downtimes || [])
        };

        const query = `
            INSERT INTO production_runs 
            (id, recipe_id, recipe_name, target_batch_size_kg, actual_produced_quantity_kg, planned_date, status, start_time, end_time, created_by, notes, has_shortages, shelf_life_months, batches, actual_ingredients_used, planned_ingredients, events, samples, suggested_transfer_pallets, downtimes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
            recipe_id=VALUES(recipe_id), recipe_name=VALUES(recipe_name), target_batch_size_kg=VALUES(target_batch_size_kg), actual_produced_quantity_kg=VALUES(actual_produced_quantity_kg),
            planned_date=VALUES(planned_date), status=VALUES(status), start_time=VALUES(start_time), end_time=VALUES(end_time), notes=VALUES(notes),
            has_shortages=VALUES(has_shortages), shelf_life_months=VALUES(shelf_life_months), batches=VALUES(batches), actual_ingredients_used=VALUES(actual_ingredients_used),
            planned_ingredients=VALUES(planned_ingredients), events=VALUES(events), samples=VALUES(samples), suggested_transfer_pallets=VALUES(suggested_transfer_pallets), downtimes=VALUES(downtimes),
            updated_at=CURRENT_TIMESTAMP
        `;

        await pool.execute(query, Object.values(runData));
        res.json({ success: true, message: 'Zlecenie zapisane pomyślnie.' });
    } catch (err) {
        console.error('Error saving production run:', err);
        res.status(500).json({ error: 'Błąd zapisu zlecenia produkcyjnego' });
    }
});

app.delete('/api/production-runs/:id', verifyToken, async (req, res) => {
    const { id } = req.params;
    try {
        await pool.execute('DELETE FROM production_runs WHERE id = ?', [id]);
        res.json({ success: true, message: 'Zlecenie usunięte.' });
    } catch (err) {
        console.error('Error deleting production run:', err);
        res.status(500).json({ error: 'Błąd usuwania zlecenia' });
    }
});

// ==========================================================
// ENDPOINTY DOSTAW I SUROWCÓW (Z database-server)
// ==========================================================

app.get('/api/deliveries', verifyToken, async (req, res) => {
    try {
        const [rows] = await pool.query('SELECT * FROM deliveries ORDER BY created_at DESC');
        res.json(normalizeRows(rows).map(row => ({
            ...row,
            items: typeof row.items === 'string' ? JSON.parse(row.items) : row.items
        })));
    } catch (err) {
        res.status(500).json({ error: 'Błąd pobierania dostaw' });
    }
});

app.get('/api/raw-materials', verifyToken, async (req, res) => {
    try {
        const [rows] = await pool.query('SELECT * FROM raw_materials');
        const normalized = normalizeRows(rows).map(r => ({
            ...r,
            currentLocation: normalizeLocation(r.currentLocation)
        }));
        res.json(normalized);
    } catch (err) {
        res.status(500).json({ error: 'Błąd pobierania surowców' });
    }
});

// ==========================================================
// ENDPOINTY INWENTARYZACJI
// ==========================================================

app.get('/api/inventory/sessions', verifyToken, async (req, res) => {
    try {
        const [sessionsRaw] = await pool.query('SELECT * FROM inventory_sessions ORDER BY created_at DESC');
        const sessions = normalizeRows(sessionsRaw);
        for (let session of sessions) {
            const [snapshots] = await pool.query('SELECT pallet_id as palletId, product_name as productName, expected_quantity as expectedQuantity, location_id as locationId FROM inventory_snapshots WHERE session_id = ?', [session.id]);
            const [scans] = await pool.query('SELECT location_id, pallet_id, counted_quantity FROM inventory_scans WHERE session_id = ?', [session.id]);
            
            const locationIds = [...new Set(snapshots.map(s => s.locationId))];
            session.locations = locationIds.map(locId => ({
                locationId: locId,
                status: scans.some(s => s.location_id === locId) ? 'scanned' : 'pending',
                scannedPallets: scans.filter(s => s.location_id === locId).map(s => ({
                    palletId: s.pallet_id,
                    countedQuantity: parseFloat(s.counted_quantity)
                }))
            }));
            session.snapshot = snapshots.map(s => ({ ...s, expectedQuantity: parseFloat(s.expectedQuantity) }));
        }
        res.json(sessions);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.post('/api/inventory/start', verifyToken, async (req, res) => {
    const { name, locations, userId } = req.body;
    const sessionId = `INV-${Date.now()}`;
    const conn = await pool.getConnection();
    try {
        await conn.beginTransaction();
        await conn.execute('INSERT INTO inventory_sessions (id, name, created_by, status) VALUES (?, ?, ?, ?)', [sessionId, name, userId, 'ongoing']);
        const [materials] = await conn.query('SELECT id, nazwa, currentWeight, currentLocation FROM raw_materials WHERE currentLocation IN (?)', [locations]);
        if (materials.length > 0) {
            const values = materials.map(m => [sessionId, m.id, m.nazwa, m.currentWeight, m.currentLocation]);
            await conn.query('INSERT INTO inventory_snapshots (session_id, pallet_id, product_name, expected_quantity, location_id) VALUES ?', [values]);
        }
        await conn.commit();
        res.json({ success: true, sessionId });
    } catch (err) {
        await conn.rollback();
        res.status(500).json({ error: err.message });
    } finally {
        conn.release();
    }
});

// ==========================================================
// SYSTEMOWE / KONFIGURACJA
// ==========================================================

app.get('/api/health', async (req, res) => {
    try {
        await pool.query('SELECT 1');
        res.json({ 
            status: 'OK', 
            database: 'connected', 
            port: PORT,
            timestamp: new Date() 
        });
    } catch (err) {
        res.status(500).json({ status: 'ERROR', database: 'disconnected', message: err.message });
    }
});

app.listen(PORT, '0.0.0.0', () => {
    console.log(`\n🚀 ZINTEGROWANY SERWER DZIAŁA: http://localhost:${PORT}`);
    console.log(`📡 POŁĄCZENIE Z BAZĄ: ${dbConfig.host}:${dbConfig.port}\n`);
});