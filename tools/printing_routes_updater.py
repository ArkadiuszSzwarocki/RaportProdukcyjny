import codecs

path = 'a:/GitHub/RaportProdukcyjny/app/blueprints/warehouse/routes/printing_routes.py'
with codecs.open(path, 'r', encoding='utf-8') as f:
    code = f.read()

old_reg = "def register_printing_routes(warehouse_bp, *, resolve_request_linia, resolve_payload_linia, update_paleta_workowanie, update_paleta_magazyn, safe_return):"
new_reg = """def register_printing_routes(warehouse_bp, *, resolve_request_linia, resolve_payload_linia, update_paleta_workowanie, update_paleta_magazyn, safe_return):

    @warehouse_bp.route('/api/printers', methods=['GET'])
    def api_printers():
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, nazwa, ip FROM drukarki WHERE aktywna = 1 ORDER BY nazwa")
            printers = cursor.fetchall()
            conn.close()
            return jsonify({'success': True, 'printers': printers})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})"""
code = code.replace(old_reg, new_reg)

with codecs.open(path, 'w', encoding='utf-8') as f:
    f.write(code)
print("Updated printing_routes.py with /api/printers")
