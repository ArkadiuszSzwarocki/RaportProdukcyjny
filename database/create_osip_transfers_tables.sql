-- Tabele dla modułu Transferów Wewnętrznych OSIP

CREATE TABLE IF NOT EXISTS osip_transfers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    transfer_code VARCHAR(50) UNIQUE NOT NULL,
    source_warehouse VARCHAR(50) NOT NULL,
    destination_warehouse VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PLANNED', -- PLANNED, IN_TRANSIT, COMPLETED, CANCELLED
    created_by VARCHAR(100) NOT NULL,
    dispatched_by VARCHAR(100) NULL,
    completed_by VARCHAR(100) NULL,
    notes TEXT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    dispatched_at DATETIME NULL,
    completed_at DATETIME NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS osip_transfer_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    transfer_id INT NOT NULL,
    pallet_id INT NULL,
    nr_palety VARCHAR(50) NULL,
    product_name VARCHAR(255) NOT NULL,
    item_type VARCHAR(20) NOT NULL DEFAULT 'raw', -- raw / fg
    requested_qty DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    loaded_qty DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    unit VARCHAR(10) NOT NULL DEFAULT 'kg',
    status VARCHAR(20) NOT NULL DEFAULT 'PLANNED',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_osip_transfer_items_transfer FOREIGN KEY (transfer_id) REFERENCES osip_transfers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
