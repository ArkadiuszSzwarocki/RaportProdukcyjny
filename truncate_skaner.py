import os

filepath = r'a:\GitHub\RaportProdukcyjny\templates\inwentaryzacja\skaner.html'
with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_content = ''.join(lines[:146]) + '''    <!-- RACK GRID SECTION -->
    {% include 'inwentaryzacja/partials/_rack_grid.html' %}

</div>
{% endblock %}

{% block scanner_modals %}
    {% include 'inwentaryzacja/partials/_modals.html' %}
{% endblock %}

{% block scanner_scripts %}
<script>
    window.INVENTORY_CONFIG = {
        sesjaId: {{ sesja_id }},
        targetLokalizacja: '{{ target_lokalizacja | default("") }}',
        url_szukaj_lokalizacji: '{{ url_for("inwentaryzacja.szukaj_lokalizacji") }}',
        url_szukaj_regalu: '{{ url_for("inwentaryzacja.szukaj_regalu") }}',
        url_szukaj_globalnie: '{{ url_for("inwentaryzacja.szukaj_globalnie") }}',
        url_zapisz_wpis: '{{ url_for("inwentaryzacja.zapisz_wpis") }}',
        url_zatwierdz_wpis: '{{ url_for("inwentaryzacja.zatwierdz_wpis") }}',
        url_zakoncz_sesje: '{{ url_for("inwentaryzacja.zakoncz_sesje") }}',
        url_print_pallet_label: '{{ url_for("warehouse_v2.print_pallet_label") }}'
    };
</script>
<script src="{{ url_for('static', filename='js/inwentaryzacja/skaner.js') }}?v={{ static_version }}"></script>
{% endblock %}
'''

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(new_content)

print('Plik skaner.html zostal pomyslnie przyciety.')
