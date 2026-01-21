<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# Mleczna-droga

This repository contains everything you need to run the app locally.

**Wersja zapoznawcza**
- **Wersja**: 0.1.0 (wersja zapoznawcza)
- **Autor**: ArkadiuszSzwarocki
- **Data**: 2026-01-05

**Opis aplikacji**
- **Cel**: System do zarządzania produkcją i magazynowaniem (m.in. receptury, zlecenia produkcyjne, mieszanki, palety, przesunięcia magazynowe).
- **Technologie**: Frontend: React + Vite; Backend: Node.js / Express; Baza danych: MySQL (skrypty w [database/schema.sql](database/schema.sql)).
- **Użytkownicy**: operatorzy produkcji, magazynierzy, planowanie produkcji i administracja.

## Run Locally

**Prerequisites:**  Node.js


1. Install dependencies:
   `npm install`
2. Copy the example env and fill real values (DO NOT commit secrets):

    - Unix / macOS:
       ```bash
       cp .env.example .env
       ```
    - Windows PowerShell:
       ```powershell
       Copy-Item .env.example .env
       ```

    Edit `.env` and set `DB_*`, `JWT_SECRET` and `VITE_API_URL` as needed. For frontend dev, `VITE_API_URL` should include `/api` (e.g. `http://localhost:8089/api` or `https://mlecznadroga.mycloudnas.com/api`).

3. Run the app:
    - Start backend only:
       ```bash
       npm run backend
       ```
    - Start frontend only:
       ```bash
       npm run frontend
       ```
    - Start both in dev mode:
       ```bash
       npm run dev
       ```

Notes:
- Backend default port: `8089` (set by `PORT` in `.env`).
- Frontend dev server default: `5173`.
- The frontend reads `VITE_API_URL` via `import.meta.env.VITE_API_URL` (see [constants.ts](constants.ts#L1)).
- `.env` and `.env.local` are included in `.gitignore` to avoid leaking secrets.
