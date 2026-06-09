from flask import render_template, request, jsonify, flash, redirect, url_for
from app.db import get_db_connection
from app.decorators import roles_required

def register_admin_warehouse_capacities_routes(admin_bp):
    @admin_bp.route('/pojemnosci_magazynu', methods=['GET', 'POST'])
    @roles_required(['admin', 'masteradmin'])
    def pojemnosci_magazynu():
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if request.method == 'POST':
            try:
                # Update capacities
                for key, value in request.form.items():
                    if key.startswith('pojemnosc_'):
                        sekcja = key.replace('pojemnosc_', '')
                        try:
                            pojemnosc = int(value)
                            cursor.execute(
                                "INSERT INTO magazyn_pojemnosci (sekcja, pojemnosc_max) VALUES (%s, %s) ON DUPLICATE KEY UPDATE pojemnosc_max = %s",
                                (sekcja, pojemnosc, pojemnosc)
                            )
                        except ValueError:
                            pass
                
                # Check for new sekcja
                new_sekcja = request.form.get('new_sekcja')
                new_pojemnosc = request.form.get('new_pojemnosc')
                if new_sekcja and new_pojemnosc:
                    try:
                        pojemnosc = int(new_pojemnosc)
                        cursor.execute(
                            "INSERT INTO magazyn_pojemnosci (sekcja, pojemnosc_max) VALUES (%s, %s) ON DUPLICATE KEY UPDATE pojemnosc_max = %s",
                            (new_sekcja, pojemnosc, pojemnosc)
                        )
                    except ValueError:
                        pass

                conn.commit()
                flash('Pojemności zostały pomyślnie zaktualizowane.', 'success')
            except Exception as e:
                conn.rollback()
                flash(f'Błąd podczas aktualizacji: {str(e)}', 'error')
            finally:
                conn.close()
                
            return redirect(url_for('admin.pojemnosci_magazynu'))

        try:
            cursor.execute("SELECT sekcja, pojemnosc_max FROM magazyn_pojemnosci ORDER BY sekcja ASC")
            pojemnosci = cursor.fetchall()
        except Exception as e:
            flash(f'Błąd pobierania danych: {str(e)}', 'error')
            pojemnosci = []
        finally:
            conn.close()

        return render_template('admin/warehouse_capacities.html', pojemnosci=pojemnosci)
