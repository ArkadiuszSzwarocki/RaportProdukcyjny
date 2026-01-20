import express from 'express';
import mysql from 'mysql2/promise';
import cors from 'cors';
import dotenv from 'dotenv';
import fs from 'fs';
import bcrypt from 'bcrypt';
import jwt from 'jsonwebtoken';
import multer from 'multer';
import pdfParse from 'pdf-parse';

dotenv.config();

// Helper: konwersja snake_case -> camelCase dla rzędów z bazy
const toCamel = (s) => s.replace(/_([a-z])/g, (_, c) => c.toUpperCase());
const normalizeRow = (row) => {
    const out = {};
    for (const k of Object.keys(row || {})) out[toCamel(k)] = row[k];
    return out;
};
const normalizeRows = (rows) => (Array.isArray(rows) ? rows.map(normalizeRow) : rows);

const app = express();
app.use(cors());
app.use(express.json());
app.use(express.text({ type: ['text/*', 'application/csv'] }));

const upload = multer({ storage: multer.memoryStorage() });

const JWT_SECRET = process.env.JWT_SECRET || 'your-secret-key-change-in-production-2024';
const BCRYPT_ROUNDS = 10;

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

const hashPassword = async (password) => await bcrypt.hash(password, BCRYPT_ROUNDS);
const comparePassword = async (password, hash) => await bcrypt.compare(password, hash);
const generateToken = (user) => jwt.sign({ id: user.id, username: user.username, role: user.role_name, subRole: user.sub_role_id }, JWT_SECRET, { expiresIn: '24h' });

const generate18DigitId = () => {
    const epoch1982 = new Date('1982-06-07T00:00:00Z').getTime();
    const diff = Math.max(0, Date.now() - epoch1982);
    const base = `${diff}`;
    const needed = 18 - base.length;
    if (needed > 0) {
        const randomPart = Math.floor(Math.random() * Math.pow(10, needed)).toString().padStart(needed, '0');
        return `${base}${randomPart}`;
    }
    return base.substring(0, 18);
};

//let dbConfig = {
   // host: process.env.DB_HOST || 'localhost',
   // port: parseInt(process.env.DB_PORT || '3307'),
   // user: process.env.DB_USER || 'root',
   // password: process.env.DB_PASSWORD || '',
  //  database: process.env.DB_NAME || 'mleczna_droga',
   // waitForConnections: true,
   // connectionLimit: 10,
  //  queueLimit: 0
//};
let dbConfig = {
    host: process.env.DB_HOST || 'localhost',
    port: parseInt(process.env.DB_PORT || '3307'), // <--- UPEWNIJ SIĘ ŻE JEST 3307
    user: process.env.DB_USER || 'root',            // <--- ZMIANA NA USERA Z DOCKERA
    password: process.env.DB_PASSWORD || 'Filipinka2010',// <--- ZMIANA NA HASŁO Z DOCKERA
    database: process.env.DB_NAME || 'MleczDroga',
    waitForConnections: true,
    connectionLimit: 10,
    queueLimit: 0
};

let pool = mysql.createPool(dbConfig);

// --- FUNKCJA INICJALIZACJI TABEL (POPRAWIONA) ---
// --- ZAKTUALIZOWANA FUNKCJA INICJALIZACJI TABEL ---
async function initTables() {
    try {
        const tableOptions = "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci";

        // 1. Tabele użytkowników i ról
        await pool.execute(`
            CREATE TABLE IF NOT EXISTS roles (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                permissions JSON
            ) ${tableOptions};
        `);

        await pool.execute(`
            CREATE TABLE IF NOT EXISTS sub_roles (
                id VARCHAR(50) PRIMARY KEY,
                role_id VARCHAR(50),
                name VARCHAR(100) NOT NULL,
                FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE
            ) ${tableOptions};
        `);

        // Wstawiamy domyślne role, jeśli ich nie ma
        const [roles] = await pool.query('SELECT * FROM roles');
        if (roles.length === 0) {
            await pool.execute(`INSERT INTO roles (id, name, permissions) VALUES 
                ('admin', 'Administrator', '["ALL"]'),
                ('magazynier', 'Magazynier', '["VIEW_WAREHOUSE", "SCAN_PALLETS"]'),
                ('planista', 'Planista', '["PLAN_PRODUCTION"]'),
                ('operator', 'Operator', '["VIEW_PRODUCTION"]')
            `);
            console.log('✅ Dodano domyślne role.');
        }

        // ... (reszta Twoich tabel: recipes, raw_materials, inventory_sessions itp.) ...
        // UPEWNIJ SIĘ, ŻE MASZ TU TEŻ RESZTĘ TABEL Z POPRZEDNIEGO KROKU
        
        console.log('✅ Baza danych zaktualizowana (role i pod-role).');
    } catch (err) {
        console.error('❌ Błąd inicjalizacji tabel:', err.message);
    }
}
// Wywołaj inicjalizację
initTables();


// --- NOWE ENDPOINTY (Dopisz to przed app.listen) ---

// Pobieranie ról
app.get('/api/roles', async (req, res) => {
    try {
        const [rows] = await pool.query('SELECT * FROM roles');
        res.json(normalizeRows(rows));
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Błąd pobierania ról' });
    }
});

// Pobieranie pod-ról (sub-roles)
app.get('/api/sub-roles', async (req, res) => {
    try {
        const [rows] = await pool.query('SELECT * FROM sub_roles');
        res.json(normalizeRows(rows));
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Błąd pobierania pod-ról' });
    }
});

// ==========================================================
// BEZPIECZNY ENDPOINT LOGOWANIA (POPRAWIONY DLA TABELI ROLES)
// ==========================================================
app.post('/api/auth/login', async (req, res) => {
    const { username, password } = req.body;

    if (!username || !password) {
        return res.status(400).json({ error: 'Wymagana nazwa użytkownika i hasło.' });
    }

    try {
        // 1. Pobierz użytkownika (u Ciebie w bazie jest role_id, a nie role)
        const [rows] = await pool.query('SELECT * FROM users WHERE username = ?', [username]);

        if (rows.length === 0) {
            return res.status(401).json({ error: 'Błędna nazwa użytkownika lub hasło.' });
        }

        const user = rows[0];

        // 2. Weryfikacja hasła
        let passwordIsValid = false;
        // Preferuj hash (może być w kolumnie `password` lub `password_hash`), fallback na plaintext
        const hashCandidate = user.password || user.password_hash || null;
        if (hashCandidate && (hashCandidate.startsWith('$2b$') || hashCandidate.startsWith('$2a$'))) {
            passwordIsValid = await bcrypt.compare(password, hashCandidate);
        } else if (hashCandidate) {
            passwordIsValid = (password === hashCandidate); // Fallback dla starych haseł przechowywanych bez hasha
        }

        if (!passwordIsValid) {
            return res.status(401).json({ error: 'Błędna nazwa użytkownika lub hasło.' });
        }

        // 3. Generowanie tokenu
        // TUTA NASTĘPUJE KLUCZOWA ZMIANA - mapujemy role_id na role
        // token: preferuj role_id/sub_role_id, fallback na role/sub_role
        const role = user.role_id || user.role || user.role_name;
        const subRole = user.sub_role_id || user.sub_role || null;

        const token = jwt.sign(
            { id: user.id, username: user.username, role, subRole },
            JWT_SECRET,
            { expiresIn: '24h' }
        );

        // Normalizujemy i wycinamy hasło
        const userNormalized = normalizeRow(user);
        delete userNormalized.password;
        userNormalized.role = role;
        if (subRole) userNormalized.subRole = subRole;

        console.log(`✅ Zalogowano użytkownika: ${username} (Rola: ${role})`);

        res.json({ token, user: userNormalized });

    } catch (err) {
        console.error('❌ Błąd logowania:', err);
        res.status(500).json({ error: 'Wystąpił błąd serwera podczas logowania.' });
    }
});

// --- KONIEC NOWYCH ENDPOINTÓW ---
initTables();

// --- API INWENTARYZACJA ---

app.get('/api/inventory/sessions', verifyToken, async (req, res) => {
    try {
        const [sessionsRaw] = await pool.query('SELECT * FROM inventory_sessions ORDER BY created_at DESC');
        const sessions = normalizeRows(sessionsRaw);
        for (let session of sessions) {
            const [snapshots] = await pool.query('SELECT pallet_id as palletId, product_name as productName, expected_quantity as expectedQuantity, location_id as locationId FROM inventory_snapshots WHERE session_id = ?', [session.id]);
            const [scans] = await pool.query('SELECT location_id, pallet_id, counted_quantity FROM inventory_scans WHERE session_id = ?', [session.id]);
            
            // Mapowanie na format frontendowy
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

app.post('/api/inventory/sessions', verifyToken, async (req, res) => {
    const { name, locationIds, createdBy } = req.body;
    const sessionId = `INV-${Date.now()}`;
    const conn = await pool.getConnection();
    try {
        await conn.beginTransaction();
        await conn.execute('INSERT INTO inventory_sessions (id, name, created_by) VALUES (?, ?, ?)', [sessionId, name, createdBy]);
        
        // Snapshot z tabeli raw_materials
        const [rows] = await conn.query('SELECT id, nazwa, currentWeight, currentLocation FROM raw_materials WHERE currentLocation IN (?)', [locationIds]);
        if (rows.length > 0) {
            const values = rows.map(r => [sessionId, r.id, r.nazwa, r.currentWeight, r.currentLocation]);
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

app.post('/api/inventory/scans', verifyToken, async (req, res) => {
    const { sessionId, locationId, palletId, countedQuantity, scannedBy } = req.body;
    try {
        await pool.execute(`
            INSERT INTO inventory_scans (session_id, location_id, pallet_id, counted_quantity, scanned_by)
            VALUES (?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE counted_quantity = VALUES(counted_quantity), scanned_at = NOW()
        `, [sessionId, locationId, palletId, countedQuantity, scannedBy]);
        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.put('/api/inventory/sessions/:id/status', verifyToken, async (req, res) => {
    const { id } = req.params;
    const { status } = req.body;
    try {
        await pool.execute('UPDATE inventory_sessions SET status = ? WHERE id = ?', [status, id]);
        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.post('/api/inventory/sessions/:id/finalize', verifyToken, async (req, res) => {
    const { id } = req.params;
    const { finalizedBy } = req.body;
    const conn = await pool.getConnection();
    try {
        await conn.beginTransaction();
        
        // 1. Pobierz wszystkie skany tej sesji
        const [scans] = await conn.query('SELECT * FROM inventory_scans WHERE session_id = ?', [id]);
        
        // 2. Pobierz snapshot tej sesji
        const [snapshots] = await conn.query('SELECT * FROM inventory_snapshots WHERE session_id = ?', [id]);
        
        // 3. Aktualizacja raw_materials na podstawie skanów
        for (const scan of scans) {
            await conn.execute(
                'UPDATE raw_materials SET currentWeight = ?, currentLocation = ?, updatedAt = NOW() WHERE id = ?',
                [scan.counted_quantity, scan.location_id, scan.pallet_id]
            );
        }
        
        // 4. Obsługa brakujących palet (te, które były w snapshocie, ale nie było ich w skanach)
        const scannedIds = scans.map(s => s.pallet_id);
        const missing = snapshots.filter(s => !scannedIds.includes(s.pallet_id));
        for (const m of missing) {
            await conn.execute(
                'UPDATE raw_materials SET currentWeight = 0, currentLocation = ?, updatedAt = NOW() WHERE id = ?',
                ['ZAGUBIONE', m.pallet_id]
            );
        }
        
        // 5. Zamknij sesję
        await conn.execute(
            'UPDATE inventory_sessions SET status = "completed", finalized_at = NOW(), finalized_by = ? WHERE id = ?',
            [finalizedBy, id]
        );
        
        await conn.commit();
        res.json({ success: true, message: 'Inwentaryzacja sfinalizowana. Stany zaktualizowane.' });
    } catch (err) {
        await conn.rollback();
        res.status(500).json({ error: err.message });
    } finally {
        conn.release();
    }
});

app.delete('/api/inventory/sessions/:id', verifyToken, async (req, res) => {
    const { id } = req.params;
    try {
        await pool.execute('DELETE FROM inventory_sessions WHERE id = ?', [id]);
        res.json({ success: true });
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

        // Pobieramy dane z raw_materials (używamy poprawnej nazwy kolumny currentLocation zamiast locationId)
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

const PORT = process.env.PORT || 5001;
app.listen(PORT, '0.0.0.0', () => {
    console.log(`🚀 SERWER API DZIAŁA: http://localhost:${PORT}`);
    console.log(`📡 Połączono z bazą: ${dbConfig.host}:${dbConfig.port}`);
});