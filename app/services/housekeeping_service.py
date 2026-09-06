"""Housekeeping Service.
Automates cleanup of temporary files, old export caches, and stale session records.
"""

import os
import time
import glob
from typing import Dict, Any


class HousekeepingService:
    """Service managing periodic file and database cleanup tasks."""

    @staticmethod
    def cleanup_temp_files(project_root: str, max_age_days: int = 30) -> Dict[str, int]:
        """Delete temporary and exported files older than max_age_days.
        
        Returns:
            Dict[str, int]: Statistics of removed files per directory
        """
        max_age_seconds = max_age_days * 86400
        now = time.time()
        stats = {'temp_files_deleted': 0, 'scratch_deleted': 0}

        target_dirs = [
            os.path.join(project_root, 'static', 'uploads', 'temp'),
            os.path.join(project_root, 'scratch')
        ]

        for directory in target_dirs:
            if not os.path.exists(directory):
                continue

            for file_path in glob.glob(os.path.join(directory, '*')):
                if not os.path.isfile(file_path):
                    continue

                try:
                    file_mtime = os.path.getmtime(file_path)
                    if now - file_mtime > max_age_seconds:
                        os.remove(file_path)
                        if 'scratch' in directory:
                            stats['scratch_deleted'] += 1
                        else:
                            stats['temp_files_deleted'] += 1
                except Exception:
                    pass

    @staticmethod
    def cleanup_old_audit_logs(retention_days: int = 180) -> Dict[str, int]:
        """Delete audit and scan logs older than retention_days to keep database lean."""
        from app.db import get_db_connection
        stats = {'palety_historia_deleted': 0, 'scanner_synced_events_deleted': 0}
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Clean old sync events
            try:
                cursor.execute(
                    "DELETE FROM scanner_synced_events WHERE created_at < DATE_SUB(NOW(), INTERVAL %s DAY)",
                    (retention_days,)
                )
                stats['scanner_synced_events_deleted'] = cursor.rowcount
            except Exception:
                pass

            # Clean old audit history
            try:
                cursor.execute(
                    "DELETE FROM palety_historia WHERE created_at < DATE_SUB(NOW(), INTERVAL %s DAY)",
                    (retention_days,)
                )
                stats['palety_historia_deleted'] = cursor.rowcount
            except Exception:
                pass

            conn.commit()
            return stats
        finally:
            cursor.close()
            conn.close()


# Singleton instance
housekeeping_service = HousekeepingService()

