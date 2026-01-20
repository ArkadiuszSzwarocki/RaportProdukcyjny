import express from 'express';
import mysql from 'mysql2/promise';
import cors from 'cors';
import dotenv from 'dotenv';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

dotenv.config({ path: path.join(__dirname, '../.env') });
import bcrypt from 'bcrypt';
import jwt from 'jsonwebtoken';

const JWT_SECRET = process.env.JWT_SECRET || 'devsecret';

const app = express();
app.use(cors());
app.use(express.json());

// Helper: konwersja snake_case -> camelCase dla wyników z DB
const toCamel = (s) => s.replace(/_([a-z])/g, (_, c) => c.toUpperCase());
const normalizeRow = (row) => {
    const out = {};
    for (const k of Object.keys(row || {})) out[toCamel(k)] = row[k];
    return out;
};
const normalizeRows = (rows) => (Array.isArray(rows) ? rows.map(normalizeRow) : rows);

// Mapowanie aliasów lokalizacji do kanonicznych identyfikatorów używanych w frontendzie
const LOCATION_ALIAS_MAP = {
    'BUFFER_MS01': 'BF_MS01',
    'BUFFER_MP01': 'BF_MP01',
    'BUFFER_MS': 'BF_MS01',
    'BUFFOR_MS01': 'BF_MS01',
    'BUFOR_MS01': 'BF_MS01',
    'BUFFER_MP': 'BF_MP01',
    'MOP01': 'MOP01',
    'PSD': 'PSD'
};
const normalizeLocation = (loc) => {
    if (!loc) return loc;
    const key = String(loc).trim().toUpperCase();
    return LOCATION_ALIAS_MAP[key] || loc;
};

// Konfiguracja bazy danych pobierana ze zmiennych środowiskowych
let dbConfig = {
    host: process.env.DB_HOST || 'localhost',
    port: parseInt(process.env.DB_PORT || '3307'),
    user: process.env.DB_USER || 'root',
    password: process.env.DB_PASSWORD || '',
    database: process.env.DB_NAME || 'mleczna_droga',
    waitForConnections: true,
    connectionLimit: 10,
    queueLimit: 0
};

let pool = mysql.createPool(dbConfig);

console.log(`\n====================================================`);
console.log(`📡 KONFIGURACJA BAZY DANYCH:`);
console.log(`   Host: ${dbConfig.host}:${dbConfig.port}`);
console.log(`   Baza: ${dbConfig.database}`);
console.log(`   Użytkownik: ${dbConfig.user}`);
console.log(`====================================================\n`);

// Endpoint do aktualizacji pliku .env i restartu połączenia
app.post('/api/config', async (req, res) => {
    const { host, port, user, password, database } = req.body;
    
    try {
        // 1. Budowanie nowej zawartości pliku .env
        const envContent = `PORT=${process.env.PORT || 5000}
DB_HOST=${host}
DB_PORT=${port}
DB_USER=${user}
DB_PASSWORD=${password}
DB_NAME=${database}`;

        // 2. Zapis do pliku .env
        const envPath = path.join(__dirname, '../.env');
        fs.writeFileSync(envPath, envContent);

        // 3. Aktualizacja konfiguracji w pamięci procesu
        dbConfig = {
            ...dbConfig,
            host,
            port: parseInt(port),
            user,
            password,
            database
        };

        // 4. Restart puli połączeń
        await pool.end();
        pool = mysql.createPool(dbConfig);

        console.log('♻️ Zaktualizowano konfigurację bazy danych i zrestartowano pulę połączeń.');
        res.json({ success: true, message: 'Konfiguracja zapisana w .env i odświeżona.' });
    } catch (err) {
        console.error('❌ Błąd aktualizacji .env:', err);
        res.status(500).json({ success: false, message: 'Błąd zapisu konfiguracji.' });
    }
});

// Endpoint Health Check
app.get('/api/health', async (req, res) => {
    try {
        const connection = await pool.getConnection();
        await connection.query('SELECT 1');
        connection.release();
        res.json({ 
            status: 'OK', 
            database: 'connected', 
            host: dbConfig.host,
            port: dbConfig.port,
            database: dbConfig.database,
            timestamp: new Date() 
        });
    } catch (err) {
        res.status(500).json({ status: 'ERROR', database: 'disconnected', message: err.message });
    }
});

// GET: Pobieranie dostaw
app.get('/api/deliveries', async (req, res) => {
    try {
        const [rows] = await pool.query('SELECT * FROM deliveries ORDER BY created_at DESC');
        const deliveries = normalizeRows(rows).map(row => ({
            ...row,
            items: typeof row.items === 'string' ? JSON.parse(row.items) : row.items
        }));
        res.json(deliveries);
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Błąd pobierania danych z bazy' });
    }
});

// GET: Pobierz surowce (raw materials / palety)
app.get('/api/raw-materials', async (req, res) => {
    try {
        // Determine available columns to avoid referencing non-existent fields
        const [cols] = await pool.query("SHOW COLUMNS FROM raw_materials");
        const colSet = new Set((cols || []).map(c => c.Field));
        const desired = ['id','nrPalety','nazwa','dataProdukcji','dataPrzydatnosci','initialWeight','currentWeight','isBlocked','blockReason','currentLocation','batchNumber','packageForm','unit','labAnalysisNotes'];
        const available = desired.filter(f => colSet.has(f));
        const createdField = colSet.has('created_at') ? 'created_at' : (colSet.has('createdAt') ? 'createdAt' : null);
        const updatedField = colSet.has('updated_at') ? 'updated_at' : (colSet.has('updatedAt') ? 'updatedAt' : null);
        const selectList = available.join(', ');
        const createdSelect = createdField ? `${createdField} as createdAt` : 'NULL as createdAt';
        const updatedSelect = updatedField ? `${updatedField} as updatedAt` : 'NULL as updatedAt';
        const sql = `SELECT ${selectList}${selectList ? ',' : ''} ${createdSelect}, ${updatedSelect} FROM raw_materials ORDER BY createdAt DESC`;
        const [rows] = await pool.query(sql);
        // Apply normalization to raw rows (handle different column namings) then convert to camelCase
        for (const r of rows) {
            const rawLoc = r.currentLocation || r.current_location || null;
            r.currentLocation = normalizeLocation(rawLoc);
        }
        const normalized = normalizeRows(rows).map(r => ({ ...r, currentLocation: normalizeLocation(r.currentLocation) }));
        res.json(normalized);
    } catch (err) {
        console.error('Błąd pobierania raw_materials:', err);
        res.status(500).json({ error: 'Błąd pobierania surowców z bazy' });
    }
});

// POST: Tworzenie nowej dostawy
app.post('/api/deliveries', async (req, res) => {
    const delivery = req.body;
    try {
        const sql = `INSERT INTO deliveries (id, orderRef, supplier, deliveryDate, status, items, createdBy, createdAt, requiresLab) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`;
        const params = [
            delivery.id || `DEL-${Date.now()}`,
            delivery.orderRef,
            delivery.supplier,
            delivery.deliveryDate,
            delivery.status,
            JSON.stringify(delivery.items),
            delivery.createdBy,
            delivery.createdAt || new Date().toISOString(),
            delivery.requiresLab ? 1 : 0
        ];
        await pool.execute(sql, params);
        res.json({ success: true, insertId: delivery.id });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Błąd zapisu w bazie danych' });
    }
});

// PUT: Aktualizacja dostawy
app.put('/api/deliveries/:id', async (req, res) => {
    const { id } = req.params;
    const delivery = req.body;
    try {
        const sql = `UPDATE deliveries SET 
                     orderRef = ?, supplier = ?, deliveryDate = ?, status = ?, 
                     items = ?, requiresLab = ? WHERE id = ?`;
        const params = [
            delivery.orderRef,
            delivery.supplier,
            delivery.deliveryDate,
            delivery.status,
            JSON.stringify(delivery.items),
            delivery.requiresLab ? 1 : 0,
            id
        ];
        await pool.execute(sql, params);
        res.json({ success: true });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Błąd aktualizacji w bazie danych' });
    }
});

// DELETE: Usuwanie dostawy
app.delete('/api/deliveries/:id', async (req, res) => {
    const { id } = req.params;
    try {
        await pool.execute('DELETE FROM deliveries WHERE id = ?', [id]);
        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ error: 'Błąd usuwania z bazy' });
    }
});

// ===== UŻYTKOWNICY (USERS) =====

// GET: Pobieranie wszystkich użytkowników
app.get('/api/users', async (req, res) => {
    try {
        const [rows] = await pool.query('SELECT * FROM users ORDER BY username');
        res.json(normalizeRows(rows));
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Błąd pobierania użytkowników' });
    }
});

// GET: Pobierz jednego użytkownika
app.get('/api/users/:id', async (req, res) => {
    const { id } = req.params;
    try {
        const [rows] = await pool.query('SELECT * FROM users WHERE id = ?', [id]);
        if (rows.length === 0) return res.status(404).json({ error: 'Użytkownik nie znaleziony' });
        res.json(normalizeRow(rows[0]));
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Błąd pobierania użytkownika' });
    }
});

// POST: Tworzenie nowego użytkownika
app.post('/api/users', async (req, res) => {
    const { id, username, password, email, role, subRole, pin, isActive } = req.body;
    try {
        const sql = `INSERT INTO users (id, username, email, role, sub_role, pin, password, isActive, createdAt) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`;
        const params = [
            id || `u-${Date.now()}`,
            username,
            email || null,
            role || 'user',
            subRole || 'AGRO',
            pin || null,
            password || 'temp123',
            isActive !== undefined ? isActive : 1,
            new Date().toISOString()
        ];
        await pool.execute(sql, params);
        res.json({ success: true, insertId: id });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Błąd tworzenia użytkownika' });
    }
});

// PUT: Aktualizacja użytkownika
app.put('/api/users/:id', async (req, res) => {
    const { id } = req.params;
    const { username, email, role, subRole, pin, password, isActive } = req.body;
    try {
        const sql = `UPDATE users SET 
                     username = ?, email = ?, role = ?, sub_role = ?, pin = ?, 
                     password = ?, isActive = ? WHERE id = ?`;
        const params = [
            username,
            email || null,
            role,
            subRole || 'AGRO',
            pin || null,
            password || null,
            isActive !== undefined ? isActive : 1,
            id
        ];
        await pool.execute(sql, params);
        res.json({ success: true });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Błąd aktualizacji użytkownika' });
    }
});

// DELETE: Usuwanie użytkownika
app.delete('/api/users/:id', async (req, res) => {
    const { id } = req.params;
    try {
        await pool.execute('DELETE FROM users WHERE id = ?', [id]);
        res.json({ success: true });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Błąd usuwania użytkownika' });
    }
});

// ==========================
// Roles & Sub-Roles endpoints
// ==========================

// GET roles
app.get('/api/roles', async (req, res) => {
    try {
        const [rows] = await pool.query('SELECT id, label FROM roles ORDER BY label');
        // Normalize to { id, name, label } where name is the role id expected by frontend
        const out = rows.map(r => ({ id: r.id, name: r.id, label: r.label }));
        res.json(out);
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Błąd pobierania ról' });
    }
});

// POST create role
app.post('/api/roles', async (req, res) => {
    const { id, label } = req.body;
    if (!id || !label) return res.status(400).json({ error: 'Id i label są wymagane' });
    try {
        await pool.execute('INSERT INTO roles (id, label) VALUES (?, ?)', [id, label]);
        res.json({ success: true });
    } catch (err) {
        console.error(err);
        if (err && err.code === 'ER_DUP_ENTRY') return res.status(409).json({ error: 'Rola już istnieje' });
        res.status(500).json({ error: 'Błąd tworzenia roli' });
    }
});

// DELETE role
app.delete('/api/roles/:id', async (req, res) => {
    const { id } = req.params;
    try {
        await pool.execute('DELETE FROM roles WHERE id = ?', [id]);
        res.json({ success: true });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Błąd usuwania roli' });
    }
});

// GET sub-roles
app.get('/api/sub-roles', async (req, res) => {
    try {
        const [rows] = await pool.query('SELECT id, name FROM sub_roles ORDER BY id');
        res.json(rows);
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Błąd pobierania oddziałów' });
    }
});

// POST create sub-role
app.post('/api/sub-roles', async (req, res) => {
    const { id, name } = req.body;
    if (!id || !name) return res.status(400).json({ error: 'Id i name są wymagane' });
    try {
        await pool.execute('INSERT INTO sub_roles (id, name) VALUES (?, ?)', [id, name]);
        res.json({ success: true });
    } catch (err) {
        console.error(err);
        if (err && err.code === 'ER_DUP_ENTRY') return res.status(409).json({ error: 'Oddział już istnieje' });
        res.status(500).json({ error: 'Błąd tworzenia oddziału' });
    }
});

// DELETE sub-role
app.delete('/api/sub-roles/:id', async (req, res) => {
    const { id } = req.params;
    try {
        await pool.execute('DELETE FROM sub_roles WHERE id = ?', [id]);
        res.json({ success: true });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Błąd usuwania oddziału' });
    }
});

// ==========================
// Login & Permissions
// ==========================

// POST login
app.post('/api/login', async (req, res) => {
    const { username, password } = req.body;
    if (!username || !password) return res.status(400).json({ error: 'Nazwa użytkownika i hasło są wymagane' });
    try {
        const [rows] = await pool.query('SELECT * FROM users WHERE username = ? LIMIT 1', [username]);
        if (!rows || rows.length === 0) return res.status(401).json({ error: 'Nieprawidłowe dane logowania' });
        const user = rows[0];
        const stored = user.password || user.pass || '';
        let ok = false;
        try { ok = await bcrypt.compare(password, stored); } catch (e) { ok = (password === stored); }
        if (!ok) {
            // fallback: plain equality
            if (password !== stored) return res.status(401).json({ error: 'Nieprawidłowe dane logowania' });
        }
        const role = user.role || user.role_id || user.roleId || 'user';
        const subRole = user.sub_role || user.subRole || 'AGRO';
        const token = jwt.sign({ id: user.id, username: user.username, role, subRole }, JWT_SECRET, { expiresIn: '8h' });
        // sanitize user payload
        const outUser = {
            id: user.id,
            username: user.username,
            role,
            subRole,
            pin: user.pin || null,
            isTemporaryPassword: user.is_temporary_password || 0
        };
        res.json({ token, user: outUser });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Błąd autoryzacji' });
    }
});

// GET permissions for user (role + individual)
app.get('/api/permissions/:userId', async (req, res) => {
    const { userId } = req.params;
    try {
        // role permissions
        const [[u]] = await pool.query('SELECT role, role_id FROM users WHERE id = ? LIMIT 1', [userId]);
        const roleId = (u && (u.role || u.role_id)) || null;
        const permissionsSet = new Set();
        if (roleId) {
            const [rp] = await pool.query('SELECT permission FROM role_permissions WHERE role_id = ?', [roleId]);
            for (const r of rp) permissionsSet.add(r.permission);
        }
        // individual permissions
        const [up] = await pool.query('SELECT permission FROM user_permissions WHERE user_id = ?', [userId]);
        for (const p of up) permissionsSet.add(p.permission);
        res.json({ permissions: Array.from(permissionsSet) });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Błąd pobierania uprawnień' });
    }
});

// POST user-permissions (replace existing)
app.post('/api/user-permissions', async (req, res) => {
    const { userId, permissions } = req.body;
    if (!userId || !Array.isArray(permissions)) return res.status(400).json({ error: 'userId i permissions są wymagane' });
    try {
        await pool.execute('DELETE FROM user_permissions WHERE user_id = ?', [userId]);
        for (const perm of permissions) {
            await pool.execute('INSERT INTO user_permissions (user_id, permission, created_at) VALUES (?, ?, NOW())', [userId, perm]);
        }
        res.json({ success: true });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Błąd zapisu uprawnień użytkownika' });
    }
});

// GET user-permissions
app.get('/api/user-permissions/:userId', async (req, res) => {
    const { userId } = req.params;
    try {
        const [rows] = await pool.query('SELECT permission FROM user_permissions WHERE user_id = ?', [userId]);
        res.json({ permissions: rows.map(r => r.permission) });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Błąd pobierania uprawnień' });
    }
});

const PORT = process.env.PORT || 5000;
app.listen(PORT, '0.0.0.0', () => {
    console.log(`\n====================================================`);
    console.log(`🚀 SERWER API DZIAŁA: http://localhost:${PORT}`);
    console.log(`📡 POŁĄCZENIE Z BAZĄ: ${dbConfig.host}:${dbConfig.port}`);
    console.log(`====================================================\n`);
});

export default app;
