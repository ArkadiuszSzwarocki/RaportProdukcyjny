import re

path = r'templates/dashboard/_dashboard_production_list.html'
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

target = '''                {% elif has_palety or has_zasypy %}
                    {% set role_lc = rola|string|trim|lower %}
                    <div id="details-{{ p[0] }}" class="details-row" style="display: {% if agro_focus_mode %}none{% elif sekcja == 'Zasyp' and role_lc in ['laborant', 'laboratorium'] %}block{% else %}none{% endif %};">
                        {% include 'dashboard/_dashboard_agro_active_details.html' %}
                    </div>
                {% endif %}'''

replacement = '''                {% else %}
                    {% include 'dashboard/_dashboard_order_card.html' %}
                    {% if has_palety or has_zasypy %}
                        {% set role_lc = rola|string|trim|lower %}
                        <div id="details-{{ p[0] }}" class="details-row" style="display: {% if agro_focus_mode %}none{% elif sekcja == 'Zasyp' and role_lc in ['laborant', 'laboratorium'] %}block{% else %}none{% endif %};">
                            {% include 'dashboard/_dashboard_agro_active_details.html' %}
                        </div>
                    {% endif %}
                {% endif %}'''

html = html.replace(target, replacement)

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)
print('Fixed missing order cards logic.')
