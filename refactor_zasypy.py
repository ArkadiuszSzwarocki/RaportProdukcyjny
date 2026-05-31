import re

path = r'templates/reports/raport_zasypow.html'
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

new_table = '''<table class="table table-hover mb-0">
                    <thead class="table-light">
                        <tr>
                            <th>Linia</th>
                            <th>Produkt</th>
                            <th>Data Zlecenia</th>
                            <th>Zasyp / Szarża</th>
                            <th>Data Zasypu</th>
                            <th>Waga Zasypu</th>
                            <th>Kto uruchomił (Zasyp)</th>
                            <th class="text-center">Dosypki</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for r in raport_data %}
                            {% set has_dosypki = r.dosypki|length > 0 %}
                            <tr {% if has_dosypki %}data-bs-toggle="collapse" data-bs-target="#details-{{ loop.index }}" style="cursor: pointer;"{% endif %}>
                                <td>
                                    <span class="badge {% if r.linia == 'AGRO' %}bg-success{% else %}bg-primary{% endif %}">
                                        {{ r.linia }}
                                    </span>
                                </td>
                                <td><strong>{{ r.produkt }}</strong><br><small class="text-muted">{{ r.nazwa_zlecenia }}</small></td>
                                <td>{{ r.data_planu }}</td>
                                <td>Zasyp: {{ r.nr_zasypu or '-' }}<br>Szarża: {{ r.nr_szarzy or '-' }}</td>
                                <td>{{ r.data_zasypu.strftime('%Y-%m-%d %H:%M') if r.data_zasypu else '-' }}</td>
                                <td><strong>{{ r.waga_zasypu|round(2) if r.waga_zasypu else '0' }} kg</strong></td>
                                <td>{{ r.zasyp_pracownik or '-' }}</td>
                                <td class="text-center">
                                    {% if has_dosypki %}
                                        <span class="badge bg-info text-dark">{{ r.dosypki|length }}</span>
                                    {% else %}
                                        <span class="text-muted">-</span>
                                    {% endif %}
                                </td>
                                <td class="text-end">
                                    {% if has_dosypki %}
                                        <i class="fas fa-chevron-down text-muted"></i>
                                    {% endif %}
                                </td>
                            </tr>
                            
                            {% if has_dosypki %}
                            <tr>
                                <td colspan="9" class="p-0 border-0">
                                    <div class="collapse" id="details-{{ loop.index }}">
                                        <div class="p-3 bg-light border-bottom">
                                            <h6 class="mb-3 text-primary"><i class="fas fa-search-plus"></i> Szczegóły dosypek dla Zasypu: <strong>{{ r.nr_zasypu or '-' }}</strong></h6>
                                            <table class="table table-sm table-bordered bg-white mb-0 shadow-sm">
                                                <thead class="table-secondary">
                                                    <tr>
                                                        <th>Składnik / Dodatek</th>
                                                        <th>Waga</th>
                                                        <th>Godzina dodania</th>
                                                        <th>Kto zlecił</th>
                                                        <th>Kto potwierdził</th>
                                                        <th>Status</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {% for dosypka in r.dosypki %}
                                                    <tr>
                                                        <td><strong>{{ dosypka.nazwa }}</strong></td>
                                                        <td>{{ dosypka.waga }} kg</td>
                                                        <td>{{ dosypka.data.strftime('%H:%M') if dosypka.data else '-' }}</td>
                                                        <td>{{ dosypka.zlecil or '-' }}</td>
                                                        <td>{{ dosypka.potwierdzil or '-' }}</td>
                                                        <td>
                                                            {% if dosypka.potwierdzone %}
                                                                <span class="badge bg-success"><i class="fas fa-check"></i> Potwierdzono</span>
                                                            {% else %}
                                                                <span class="badge bg-warning text-dark"><i class="fas fa-clock"></i> Oczekuje</span>
                                                            {% endif %}
                                                        </td>
                                                    </tr>
                                                    {% endfor %}
                                                </tbody>
                                            </table>
                                        </div>
                                    </div>
                                </td>
                            </tr>
                            {% endif %}
                            
                        {% else %}
                            <tr>
                                <td colspan="9" class="text-center py-4 text-muted">Brak danych dla wybranego zakresu.</td>
                            </tr>
                        {% endfor %}
                    </tbody>
                </table>'''

html = re.sub(r'<table class="table table-hover mb-0">.*?</table>', new_table, html, flags=re.DOTALL)

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)
print('Replaced table with collapsible detailed view.')
