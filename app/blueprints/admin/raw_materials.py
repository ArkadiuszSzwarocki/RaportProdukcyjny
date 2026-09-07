from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.db import get_db_connection

def register_admin_raw_materials_routes(admin_bp):

    @admin_bp.route('/admin/slownik-surowcow', methods=['GET'])
    def raw_materials_index():
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM slownik_surowcow ORDER BY nazwa ASC")
            items = cursor.fetchall()
        finally:
            conn.close()
        return render_template('admin/raw_materials.html', items=items)

    @admin_bp.route('/admin/slownik-surowcow/zapisz', methods=['POST'])
    def raw_materials_save():
        data = request.form
        item_id = data.get('id')
        nazwa = data.get('nazwa', '').strip()
        symbol = data.get('symbol', '').strip()
        typ = data.get('typ', 'surowiec')

        if not nazwa:
            flash("Nazwa jest wymagana.", "danger")
            return redirect(url_for('admin.raw_materials_index'))

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            if item_id:
                cursor.execute("""
                    UPDATE slownik_surowcow 
                    SET nazwa = %s, symbol = %s, typ = %s 
                    WHERE id = %s
                """, (nazwa, symbol, typ, item_id))
            else:
                cursor.execute("""
                    INSERT INTO slownik_surowcow (nazwa, symbol, typ) 
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE symbol = VALUES(symbol), typ = VALUES(typ)
                """, (nazwa, symbol, typ))
            conn.commit()
            flash("Zapisano pomyślnie.", "success")
        except Exception as e:
            conn.rollback()
            flash(f"Błąd podczas zapisu: {str(e)}", "danger")
        finally:
            conn.close()
        
        return redirect(url_for('admin.raw_materials_index'))

    @admin_bp.route('/admin/slownik-surowcow/usun/<int:item_id>', methods=['POST'])
    def raw_materials_delete(item_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM slownik_surowcow WHERE id = %s", (item_id,))
            conn.commit()
            flash("Usunięto pomyślnie.", "success")
        except Exception as e:
            conn.rollback()
            flash(f"Błąd podczas usuwania: {str(e)}", "danger")
        finally:
            conn.close()
        return redirect(url_for('admin.raw_materials_index'))
