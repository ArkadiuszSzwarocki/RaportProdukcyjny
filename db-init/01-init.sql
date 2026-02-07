-- Optional initialization script for MySQL
-- This script runs when MySQL container starts for the first time
-- It's automatically executed because it's in docker-entrypoint-initdb.d/

-- Set character set and collation
-- ALTER DATABASE raportprodukcyjny CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Optional: Create indexes for performance
-- These can be part of the main schema creation in db.setup_database()

-- Optional: Insert test data (if needed for development)
-- INSERT INTO users (username, email, password_hash, role) VALUES 
-- ('admin', 'admin@example.com', '[hashed_password]', 'admin');

-- Optional: Create views or stored procedures
-- CREATE VIEW active_plans AS
-- SELECT * FROM plan_produkcji WHERE status = 'active';

-- Additional initialization can go here
-- But most schema creation should be handled by app/db.py::setup_database()
