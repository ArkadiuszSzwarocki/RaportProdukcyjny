"""Read historical report deliveries without generating or sending reports."""
from datetime import date
from app.db import get_db_connection


def load_report_deliveries(line='ALL'):
    connection=get_db_connection()
    cursor=connection.cursor(dictionary=True)
    try:
        query='SELECT * FROM auto_report_history'
        args=()
        if line in ('AGRO','PSD'):
            query+=' WHERE linia=%s'
            args=(line,)
        cursor.execute(query+' ORDER BY created_at DESC LIMIT 100',args)
        rows=cursor.fetchall()
        for row in rows:
            current_line=str(row.get('linia') or '')
            try:
                report_date=date.fromisoformat(str(row.get('data_raportu'))[:10]).isoformat()
            except ValueError:
                report_date=None
            row['pdf_filename']=f'Raport_{current_line}_{report_date}.pdf' if current_line in ('AGRO','PSD') and report_date else None
            row['xls_filename']=f'Raport_{current_line}_{report_date}.xlsx' if row['pdf_filename'] else None
        return rows,True
    except Exception as error:
        if getattr(error,'errno',None)==1146:
            return [],False
        raise
    finally:
        cursor.close()
        connection.close()
