"""Database error handling decorator for Flask routes."""

from functools import wraps
from flask import current_app, flash, redirect, url_for
from app.db import get_db_connection
import logging

logger = logging.getLogger(__name__)


def with_db_transaction(func):
    """
    Decorator that handles DB transaction lifecycle automatically.
    
    Features:
    - Opens DB connection and cursor
    - Passes (conn, cursor) to function
    - Handles commit/rollback automatically
    - Logs errors with full traceback
    - Cleans up resources in finally block
    
    Usage:
        @with_db_transaction
        def my_route(conn, cursor):
            cursor.execute("SELECT ...")
            return render_template(...)
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            logger.debug(f"DB transaction started for {func.__name__}")
            
            # Call the decorated function with conn and cursor
            result = func(conn, cursor, *args, **kwargs)
            
            # If we got here, commit the transaction
            conn.commit()
            logger.debug(f"DB transaction committed for {func.__name__}")
            return result
            
        except Exception as e:
            # Log the full error
            logger.error(
                f"Error in {func.__name__}: {str(e)}",
                exc_info=True,
                extra={'route': func.__name__}
            )
            
            # Try to rollback
            if conn:
                try:
                    conn.rollback()
                    logger.debug(f"DB transaction rolled back for {func.__name__}")
                except Exception as rollback_err:
                    logger.warning(f"Failed to rollback in {func.__name__}: {rollback_err}")
            
            # Show error to user
            flash(f"❌ Błąd: {str(e)[:100]}", 'danger')
            return redirect(url_for('main.index'))
            
        finally:
            if conn:
                try:
                    cursor.close() if 'cursor' in locals() else None
                    conn.close()
                    logger.debug(f"DB resources closed for {func.__name__}")
                except Exception as close_err:
                    logger.warning(f"Failed to close DB resources in {func.__name__}: {close_err}")
    
    return wrapper
