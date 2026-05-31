import os

def read_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def write_file(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

base_dir = r"c:\Users\arkad\Documents\GitHub\RaportProdukcyjny\templates\dashboard"

# 1. Update _dashboard_agro_machine_stats.html to be HORIZONTAL
machine_stats_html = """{% if p[3] == 'w toku' and linia == 'AGRO' %}
<div class="machine-stats-horizontal">
    <div class="machine-stat-item">
        <span class="stat-label">STATUS MASZYNY</span>
        <div class="machine-status-pill status-offline" data-machine-status-pill style="background: #ef4444; color: white; border: 1px solid #dc2626; font-weight: 700;">OFFLINE</div>
    </div>
    <div class="machine-stat-item" style="display: none;" data-machine-wrapped-indicator>
        <span class="stat-label">OWIJARKA</span>
        <div class="badge" style="background: #94a3b8; color: white; font-weight: bold; padding: 4px 12px; border-radius: 12px; font-size: 0.85em; display: inline-block;">...</div>
    </div>
    <div class="machine-stat-item">
        <span class="stat-label">LICZNIK SZTUK (GLOBALNY)</span>
        <div class="machine-counter-pill" data-machine-counter-pill data-counter-type="global" style="background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; font-weight: 600;">0 szt.</div>
    </div>
    <div class="machine-stat-item">
        <span class="stat-label">LICZNIK SZTUK (BIEŻĄCE ZLECENIE)</span>
        <div class="machine-counter-pill" data-machine-counter-pill data-counter-type="real" style="background: #f8fafc; color: #1e293b; border: 1px solid #cbd5e1; font-weight: 800; font-size: 1.1em;">0 szt.</div>
    </div>
    <div class="machine-stat-item">
        <span class="stat-label">LICZNIK PALET (SYSTEM)</span>
        {% set current_pal_count = (palety_mapa.get(p[0], [])|length if palety_mapa else 0) %}
        <div class="machine-pallet-count-pill" style="background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; font-weight: 800; font-size: 1.1em; width: fit-content; padding: 6px 14px; border-radius: 8px;">{{ current_pal_count }} szt.</div>
    </div>
</div>

<style>
.machine-stats-horizontal {
    display: flex;
    gap: 15px;
    align-items: center;
    background: #ffffff;
    padding: 10px 15px;
    border-radius: 12px;
    border: 1px solid #e2e8f0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    flex-wrap: wrap;
}
.machine-stat-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
}
.machine-stat-item .stat-label {
    font-size: 0.65em;
    font-weight: 800;
    color: #64748b;
    text-transform: uppercase;
}
.machine-counter-pill, .machine-status-pill, .machine-pallet-count-pill {
    padding: 4px 12px;
    border-radius: 99px;
    white-space: nowrap;
}
</style>
{% endif %}"""

write_file(os.path.join(base_dir, "_dashboard_agro_machine_stats.html"), machine_stats_html)

# 2. Extract TOP BAR elements into a new file: _dashboard_agro_top_bar.html
top_bar_html = """{% if sekcja|string|trim|lower == 'workowanie' and linia|string|trim|upper == 'AGRO' and agro_focus_mode and workowanie_rozliczenie_ctx and workowanie_rozliczenie_ctx.is_active_plan %}
{% set wrctx = workowanie_rozliczenie_ctx %}
<div class="agro-active-top-bar" style="display: flex; gap: 15px; flex-wrap: wrap; align-items: stretch; margin-bottom: 15px;">
    
    <!-- Left: Rozliczenie MIX and Raport -->
    <div style="display: flex; gap: 10px; align-items: stretch;">
        <a href="{{ url_for('production.agro_mix_rozliczenie_page', data=dzisiaj) }}" class="btn-wrs" style="background: #9b59b6; text-decoration: none; text-align: center; border-radius: 8px; padding: 0 20px; color: #fff; font-weight: 700; display: flex; align-items: center; gap: 6px; box-shadow: 0 2px 6px rgba(155,89,182,0.3);" data-slide>
            <span class="material-icons" style="font-size: 20px;">blender</span> Rozliczenie MIX
        </a>
        <a href="{{ url_for('agro_warehouse.raport_palet', data=dzisiaj, select=1) }}" class="btn-wrs" style="background: #3498db; text-decoration: none; text-align: center; border-radius: 8px; padding: 0 20px; color: #fff; font-weight: 700; display: flex; align-items: center; gap: 6px; box-shadow: 0 2px 6px rgba(52,152,219,0.3);">
            <span class="material-icons" style="font-size: 20px;">print</span> Raport
        </a>
    </div>

    <!-- Middle: Podepnij material dropdown -->
    {% if wrctx.active_plan and wrctx.all_warehouse_packaging %}
    <div style="display: flex; gap: 10px; align-items: center; background: #fff; padding: 8px 15px; border-radius: 12px; border: 1px solid #e2e8f0; box-shadow: 0 2px 8px rgba(0,0,0,0.05); flex: 1;">
        <span style="font-size: 0.85em; font-weight: 700; color: #27ae60; white-space: nowrap;">Podepnij materiał / folię:</span>
        <select id="select_warehouse_packaging" class="form-control" style="flex: 1; border-radius: 8px; height: 36px; border: 1px solid #c2ebd0; font-size: 0.9em; min-width: 200px;">
            <option value="">-- Wybierz materiał z magazynu --</option>
            {% for item in wrctx.all_warehouse_packaging %}
                <option value="{{ item.id }}" data-nazwa="{{ item.nazwa|e }}" data-stan="{{ item.stan_magazynowy|int }}" data-lokalizacja="{{ item.lokalizacja|e if item.lokalizacja else '' }}">
                    {{ item.nazwa }} (Stan: {{ item.stan_magazynowy|int }} szt/kg){% if item.lokalizacja %} - {{ item.lokalizacja }}{% endif %}
                </option>
            {% endfor %}
        </select>
        <button class="btn btn-primary" style="height: 36px; padding: 0 16px; display: inline-flex; align-items: center; gap: 5px; font-weight: 700; font-size: 0.85em; background: #27ae60; border-color: #27ae60; color: #fff; border-radius: 8px; cursor: pointer; white-space: nowrap;" onclick="var select = document.getElementById('select_warehouse_packaging'); if(!select.value) { alert('Wybierz materiał!'); return; } linkPackaging(select.value, {{ wrctx.active_plan.id }});">
            <span class="material-icons" style="font-size: 18px;">add_circle</span> PODEPNIJ MATERIAŁ
        </button>
    </div>
    {% endif %}

    <!-- Right: Machine Stats -->
    <div style="margin-left: auto;">
        {% include 'dashboard/_dashboard_agro_machine_stats.html' %}
    </div>

</div>
{% endif %}"""
write_file(os.path.join(base_dir, "_dashboard_agro_top_bar.html"), top_bar_html)

# 3. Clean up _dashboard_agro_settlement.html (Remove buttons & PODEPNIJ MATERIAŁ section)
settlement_path = os.path.join(base_dir, "_dashboard_agro_settlement.html")
settlement_html = read_file(settlement_path)

# Remove the buttons block:
import re
settlement_html = re.sub(r'<div style="display: flex; gap: 10px; margin-bottom: 14px;">.*?</div>\s*<div class="work-form">', r'<div class="work-form">', settlement_html, flags=re.DOTALL)
# Remove the Podepnięcie materiału block:
settlement_html = re.sub(r'<!-- PODPIĘCIE NOWEGO MATERIAŁU/FOLII Z MAGAZYNU -->.*?{% endif %}', r'', settlement_html, flags=re.DOTALL)

write_file(settlement_path, settlement_html)

# 4. Modify _dashboard_production_list.html to support the two column grid for active order
prod_list_path = os.path.join(base_dir, "_dashboard_production_list.html")
prod_list_html = read_file(prod_list_path)

replacement = """                    <div id="details-{{ p[0] }}" class="active-agro-details-direct-wrapper">
                        {% if sekcja == 'Workowanie' and linia == 'AGRO' %}
                            {% include 'dashboard/_dashboard_agro_top_bar.html' %}
                            <div class="active-agro-split-layout" style="display: grid; grid-template-columns: minmax(400px, 1fr) minmax(400px, 1.2fr); gap: 20px; align-items: start;">
                                <div class="agro-split-left" style="display: flex; flex-direction: column; gap: 15px;">
                                    {% include 'dashboard/_dashboard_order_card.html' %}
                                    {% include 'dashboard/_dashboard_agro_settlement.html' %}
                                </div>
                                <div class="agro-split-right">
                                    {% include 'dashboard/_dashboard_agro_active_details.html' %}
                                </div>
                            </div>
                        {% else %}
                            {% include 'dashboard/_dashboard_order_card.html' %}
                            <div class="active-agro-details-direct" style="margin-top: 15px;">
                                {% include 'dashboard/_dashboard_agro_active_details.html' %}
                            </div>
                        {% endif %}
                    </div>"""

# Replace in the 3 locations where it handles active order details
pattern_to_replace = r"{% include 'dashboard/_dashboard_order_card\.html' %}\s*({% set has_palety =.*?%})\s*({% set has_zasypy =.*?%})\s*({% if sekcja in \['Zasyp', 'Workowanie'\] and not active_szarze_panel\.rendered %})\s*({% set active_szarze_panel\.rendered = true %})\s*<div id=\"details-{{ p\[0\] }}\" class=\"active-agro-details-direct\">\s*{% if sekcja == 'Workowanie' and linia == 'AGRO' %}\s*{% include 'dashboard/_dashboard_agro_machine_stats\.html' %}\s*{% include 'dashboard/_dashboard_agro_active_details\.html' %}\s*{% include 'dashboard/_dashboard_agro_settlement\.html' %}\s*{% else %}\s*{% include 'dashboard/_dashboard_agro_active_details\.html' %}\s*{% endif %}\s*</div>"

# Actually, the original structure had {% include 'dashboard/_dashboard_order_card.html' %} outside the IF blocks.
# Let's just target the whole block.
# Wait, let's use a simple string replace for the `<div id="details-{{ p[0] }}" class="active-agro-details-direct">` block.
# But wait, `{% include 'dashboard/_dashboard_order_card.html' %}` is placed right before it! We need to consume it or change it.
"""

write_file(r"c:\Users\arkad\Documents\GitHub\RaportProdukcyjny\refactor_agro.py", CodeContent)
