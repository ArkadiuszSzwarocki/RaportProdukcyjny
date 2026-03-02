"""Database connection context manager with automatic cleanup and logging."""

from contextlib import contextmanager
from app.db import get_db_connection
import logging

logger = logging.getLogger(__name__)


@contextmanager
def db_connection(name: str = "unnamed"):
    """
    Context manager for safe database connections with automatic cleanup.
    
    Usage:
        with db_connection("my_function") as (conn, cursor):
            cursor.execute("SELECT ...")
            # No need to close, it's automatic!
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        logger.debug(f"DB connection opened for {name}")
        yield conn, cursor
    except Exception as e:
        logger.error(f"DB error in {name}: {str(e)}", exc_info=True)
        if conn:
            try:
                conn.rollback()
            except:
                pass
        raise
    finally:
        try:
            if cursor:
                cursor.close()
                logger.debug(f"Cursor closed for {name}")
        except Exception as e:
            logger.warning(f"Error closing cursor in {name}: {str(e)}")
        
        try:
            if conn:
                conn.close()
                logger.debug(f"Connection closed for {name}")
        except Exception as e:
            logger.warning(f"Error closing connection in {name}: {str(e)}")
