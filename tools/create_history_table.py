import mysql.connector
import sys
sys.path.append('.')
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

create_table_sql = """
CREATE TABLE IF NOT EXISTS `magazyn_opakowania_historia` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `oryginalny_id` int(11) DEFAULT NULL,
  `nr_palety` varchar(50) DEFAULT NULL,
  `nazwa` varchar(255) NOT NULL,
  `stan_magazynowy` float DEFAULT 0,
  `lokalizacja` varchar(64) DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `nr_partii` varchar(100) DEFAULT NULL,
  `data_produkcji` date DEFAULT NULL,
  `data_przydatnosci` date DEFAULT NULL,
  `typ_opakowania` varchar(50) DEFAULT 'bags',
  `is_blocked` tinyint(1) DEFAULT 0,
  `linia` varchar(10) DEFAULT 'PSD',
  PRIMARY KEY (`id`),
  KEY `idx_moh_nazwa` (`nazwa`(250)),
  KEY `idx_moh_oryg_id` (`oryginalny_id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4;
"""

try:
    cursor.execute(create_table_sql)
    conn.commit()
    print("Table magazyn_opakowania_historia created successfully.")
except Exception as e:
    print(f"Error: {e}")
finally:
    cursor.close()
    conn.close()
