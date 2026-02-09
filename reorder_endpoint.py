"""Standalone code for reorder endpoint - to add to routes_planning.py"""

# Add this endpoint code to routes_planning.py

CODE = '''
@planning_bp.route('/api/reorder_plans_bulk', methods=['POST'])
@roles_required('planista', 'admin')
def reorder_plans_bulk():
    """Bulk reorder plans via AJAX/drag-drop."""
    try:
        data = request.get_json(force=True)
    except Exception:
        data = request.form.to_dict()
    
    plan_ids = data.get('plan_ids', [])
    data_planu = data.get('data')
    
    if not plan_ids or not isinstance(plan_ids, list):
        return jsonify({'success': False, 'message': 'plan_ids required'}), 400
    if not data_planu:
        return jsonify({'success': False, 'message': 'data required'}), 400
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Reassign sequences 1,2,3,... in dragged order
        for idx, pid in enumerate(plan_ids, 1):
            cursor.execute(
                "UPDATE plan_produkcji SET kolejnosc=%s WHERE id=%s AND DATE(data_planu)=%s",
                (idx, int(pid), data_planu)
            )
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'reordered'}), 200
        
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except:
            pass
        return jsonify({'success': False, 'message': str(e)}), 500
'''

if __name__ == '__main__':
    print("Code ready to add")
