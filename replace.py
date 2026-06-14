import sys

filepath = r'a:\GitHub\RaportProdukcyjny\templates\dashboard\_dashboard_production_list.html'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

start_marker = '{# 2. Startable planned orders #}'
end_marker = '{% endif %}\n    </div>\n\n<!-- Modular Modal for Read-Only Plan Preview -->'

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print('Markers not found')
    sys.exit(1)

new_code = '''<div class="planned-orders-table-wrapper" style="overflow-x: auto;">
<table class="table" style="width: 100%; background: #fff; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border-collapse: collapse;">
    <thead style="background: #f8fafc; border-bottom: 2px solid #e2e8f0;">
        <tr>
            <th style="padding: 12px 16px; text-align: left; color: #475569; font-weight: 600;">Lp. / Zlecenie</th>
            <th style="padding: 12px 16px; text-align: left; color: #475569; font-weight: 600;">Status / Data</th>
            <th style="padding: 12px 16px; text-align: left; color: #475569; font-weight: 600;">Plan / Wykonanie</th>
            <th style="padding: 12px 16px; text-align: left; color: #475569; font-weight: 600;">Parametry</th>
            <th style="padding: 12px 16px; text-align: right; color: #475569; font-weight: 600;">Akcje</th>
        </tr>
    </thead>
    <tbody>
        {# 2. Startable planned orders #}
        {% for p in plan if p[3]|lower == 'zaplanowane' and ((sekcja == 'Workowanie' and allowed_work_start_ids is defined and p[0] in allowed_work_start_ids) or (sekcja == 'Zasyp' and allowed_zasyp_start_ids is defined and p[0] in allowed_zasyp_start_ids)) %}
            {% set g_loop_idx.val = g_loop_idx.val + 1 %}
            {% set order_index = g_loop_idx.val %}
            {% set has_palety = (palety_mapa.get(p[0], [])|length > 0 if palety_mapa is defined and palety_mapa else false) %}
            {% set has_zasypy = (palety_mapa.get(p[0], [])|length > 0 if (sekcja == 'Zasyp' and palety_mapa is defined and palety_mapa) else false) %}
            {% include 'dashboard/_dashboard_order_table_row.html' %}
        {% endfor %}
        
        {# 3. Other planned orders #}
        {% for p in plan if p[3]|lower == 'zaplanowane' and not ((sekcja == 'Workowanie' and allowed_work_start_ids is defined and p[0] in allowed_work_start_ids) or (sekcja == 'Zasyp' and allowed_zasyp_start_ids is defined and p[0] in allowed_zasyp_start_ids)) %}
            {% set g_loop_idx.val = g_loop_idx.val + 1 %}
            {% set order_index = g_loop_idx.val %}
            {% set has_palety = (palety_mapa.get(p[0], [])|length > 0 if palety_mapa is defined and palety_mapa else false) %}
            {% set has_zasypy = (palety_mapa.get(p[0], [])|length > 0 if (sekcja == 'Zasyp' and palety_mapa is defined and palety_mapa) else false) %}
            {% include 'dashboard/_dashboard_order_table_row.html' %}
        {% endfor %}
        
        {# 4. Completed/other orders #}
        {% for p in plan if p[3]|lower not in ['w toku', 'zaplanowane'] %}
            {% set g_loop_idx.val = g_loop_idx.val + 1 %}
            {% set order_index = g_loop_idx.val %}
            {% set has_palety = (palety_mapa.get(p[0], [])|length > 0 if palety_mapa is defined and palety_mapa else false) %}
            {% set has_zasypy = (palety_mapa.get(p[0], [])|length > 0 if (sekcja == 'Zasyp' and palety_mapa is defined and palety_mapa) else false) %}
            {% include 'dashboard/_dashboard_order_table_row.html' %}
        {% endfor %}
    </tbody>
</table>
</div>
'''

new_content = content[:start_idx] + new_code + content[end_idx:]

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(new_content)

print('Success')
