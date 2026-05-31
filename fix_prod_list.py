import re

content = open('templates/dashboard/_dashboard_production_list.html', encoding='utf-8').read()

correct_body = """                {% set g_loop_idx.val = g_loop_idx.val + 1 %}
                {% set order_index = g_loop_idx.val %}
                {% include 'dashboard/_dashboard_order_card.html' %}
                
                {% set has_palety = (palety_mapa.get(p[0], [])|length > 0 if palety_mapa is defined and palety_mapa else false) %}
                {% set has_zasypy = (palety_mapa.get(p[0], [])|length > 0 if (sekcja == 'Zasyp' and palety_mapa is defined and palety_mapa) else false) %}
                
                {% if sekcja in ['Zasyp', 'Workowanie'] and ns.is_active and p[0] == ns.active_plan_id and not active_szarze_panel.rendered %}
                    {% set active_szarze_panel.rendered = true %}
                    <style>.cards .active-agro-details-direct-wrapper { grid-column: 1 / -1 !important; width: 100% !important; max-width: 100% !important; }
                    @media (max-width: 900px) { .active-agro-split-layout { grid-template-columns: 1fr !important; } }</style>
                    <div id="details-{{ p[0] }}" class="active-agro-details-direct-wrapper" style="width: 100%;">
                        {% if sekcja == 'Workowanie' and linia == 'AGRO' %}
                            {% include 'dashboard/_dashboard_agro_top_bar.html' %}
                            {% set wrctx = workowanie_rozliczenie_ctx %}
                            <div class="active-agro-split-layout" style="display: flex; flex-wrap: wrap; gap: 20px; align-items: flex-start;">
                                <div class="agro-split-left" style="flex: 1 1 500px; min-width: 0; display: flex; flex-direction: column; gap: 15px;">
                                    <!-- Podepnij material dropdown -->
                                    {% if wrctx and wrctx.active_plan and wrctx.all_warehouse_packaging %}
                                    <div style="display: flex; gap: 10px; align-items: center; background: #fff; padding: 8px 15px; border-radius: 12px; border: 1px solid #e2e8f0; box-shadow: 0 2px 8px rgba(0,0,0,0.05); width: 100%; box-sizing: border-box;">
                                        <span style="font-size: 0.85em; font-weight: 700; color: #27ae60; white-space: nowrap;">Podepnij materiał / folię:</span>
                                        <select id="select_warehouse_packaging" class="form-control" style="flex: 1; border-radius: 8px; height: 36px; border: 1px solid #c2ebd0; font-size: 0.9em; min-width: 200px;">
                                            <option value="">-- Wybierz materiał z magazynu --</option>
                                            {% for item in wrctx.all_warehouse_packaging %}
                                                <option value="{{ item.id }}" data-nazwa="{{ item.nazwa|e }}" data-stan="{{ item.stan_magazynowy|int }}" data-lokalizacja="{{ item.lokalizacja|e if item.lokalizacja else '' }}">
                                                    {{ item.nazwa }} (Stan: {{ item.stan_magazynowy|int }} szt/kg){% if item.lokalizacja %} - {{ item.lokalizacja }}{% endif %}
                                                </option>
                                            {% endfor %}
                                        </select>
                                        <button class="btn btn-primary" style="height: 36px; padding: 0 16px; display: inline-flex; align-items: center; gap: 5px; font-weight: 700; font-size: 0.85em; background: #27ae60; border-color: #27ae60; color: #fff; border-radius: 8px; cursor: pointer; white-space: nowrap; border: none;" onclick="var select = document.getElementById('select_warehouse_packaging'); if(!select.value) { alert('Wybierz materiał!'); return; } linkPackaging(select.value, {{ wrctx.active_plan.id }});">
                                            <span class="material-icons" style="font-size: 18px;">add_circle</span> PODEPNIJ MATERIAŁ
                                        </button>
                                    </div>
                                    {% endif %}
                                    
                                    {% include 'dashboard/_dashboard_order_card.html' %}
                                    {% include 'dashboard/_dashboard_agro_settlement.html' %}
                                </div>
                                <div class="agro-split-right" style="display: flex; flex-direction: column; gap: 15px;">
                                    {% include 'dashboard/_dashboard_agro_machine_stats.html' %}
                                    {% include 'dashboard/_dashboard_agro_active_details.html' %}
                                </div>
                            </div>
                        {% else %}
                            {% include 'dashboard/_dashboard_order_card.html' %}
                            <div class="active-agro-details-direct" style="margin-top: 15px;">
                                {% include 'dashboard/_dashboard_agro_active_details.html' %}
                            </div>
                        {% endif %}
                    </div>
                {% elif has_palety or has_zasypy %}
                    {% set role_lc = rola|string|trim|lower %}
                    <div id="details-{{ p[0] }}" class="details-row" style="display: {% if agro_focus_mode %}none{% elif sekcja == 'Zasyp' and role_lc in ['laborant', 'laboratorium'] %}block{% else %}none{% endif %};">
                        {% include 'dashboard/_dashboard_agro_active_details.html' %}
                    </div>
                {% endif %}"""

new_content = """{# Renders the production plan cards and handles AGRO focus mode layout #}
{% if sekcja != 'Magazyn' %}
    <style>
        /* Active Agro Details Side-by-Side Layout */
        .active-agro-details-direct {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
            align-items: start;
            width: 100%;
            flex: 2 1 250px;
        }

        .active-agro-details-direct .active-order-szarze-panel {
            width: 100% !important;
            max-width: 100% !important;
        }

        @media (min-width: 1400px) {
            .cards.agro-focus-mode .active-agro-details-direct {
                grid-column: 2 / -1;
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 15px;
                align-items: start;
                width: 100%;
            }
        }
        
        /* AGGRESSIVE MOBILE OVERRIDES TO ENSURE NO OVERFLOW */
        @media screen and (max-width: 600px) {
            .cards {
                display: flex !important;
                flex-direction: column !important;
                width: 100% !important;
                max-width: 100vw !important;
                padding: 4px 0 !important;
                margin: 0 !important;
            }
            .cards .card {
                width: 100% !important;
                max-width: 100vw !important;
                margin-left: 0 !important;
                margin-right: 0 !important;
                flex: none !important;
            }
            .active-agro-details-direct, .details-row {
                width: 100% !important;
                max-width: 100vw !important;
                box-sizing: border-box !important;
                padding: 4px !important;
                margin: 0 !important;
                display: block !important;
            }
            .active-order-szarze-panel {
                width: 100% !important;
                max-width: 100% !important;
                padding: 8px !important;
                box-sizing: border-box !important;
            }
            .active-order-szarze-line {
                flex-direction: column !important;
                align-items: flex-start !important;
                gap: 6px !important;
                padding: 4px 0 !important;
            }
            .active-order-szarze-left {
                width: 100% !important;
                flex-wrap: wrap !important;
            }
            .active-order-szarze-actions {
                width: 100% !important;
                justify-content: flex-start !important;
                margin-top: 4px !important;
            }
            .active-order-szarze-actions > div {
                flex-wrap: wrap !important;
                width: 100% !important;
            }
            .active-order-szarze-actions .btn-action {
                flex: 1 1 auto;
                text-align: center;
                padding: 4px 8px !important;
                font-size: 0.65rem !important;
            }
        }
    </style>
    
    <div id="dashboard-production-section" class="cards {% if agro_focus_mode %}agro-focus-mode{% endif %}">
        {% if agro_focus_mode and not (sekcja == 'Workowanie' and linia == 'AGRO') %}
        <div class="toggle-focus-wrapper" style="grid-column: 1 / -1; margin-bottom: 8px; display: flex; justify-content: flex-start;">
            <button id="toggle-focus-plan-btn" class="btn-action btn-outline-secondary" style="display: inline-flex; align-items: center; gap: 6px; font-size: 0.85em; padding: 6px 12px; border-radius: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);" onclick="window.toggleFocusPlan(this)">
                <span class="material-icons" style="font-size: 18px;">visibility</span> <span class="btn-text">Pokaż ukryte zlecenia</span>
            </button>
        </div>
        {% endif %}
        
        {% if agro_focus_mode %}
        <script>
            window.toggleFocusPlan = function(btn) {
                var modal = document.getElementById('plan-preview-modal');
                if (modal) { modal.style.display = 'flex'; }
            };
            window.closePlanPreviewModal = function() {
                var modal = document.getElementById('plan-preview-modal');
                if (modal) { modal.style.display = 'none'; }
            };
            window.addEventListener('click', function(event) {
                var modal = document.getElementById('plan-preview-modal');
                if (event.target === modal) { modal.style.display = 'none'; }
            });
        </script>
        {% endif %}
        
        {% if not plan %}
        <div class="no-orders-alert animate__animated animate__pulse animate__infinite" style="width: 100%; grid-column: 1 / -1;">
            <span class="material-icons info-icon" style="font-size: 48px; color: #f59e0b;">error_outline</span>
            <div class="alert-content" style="flex: 1;">
                <strong style="display: block; font-size: 18px; margin-bottom: 8px; color: #92400e;">Brak zaplanowanych zleceń!</strong>
                <p style="color: #b45309; margin-bottom: 16px; font-size: 14px; line-height: 1.5;">Nie znaleziono zleceń na dzisiaj w sekcji {{ sekcja }}. Skontaktuj się z planistą, aby zaplanował produkcję.</p>
                <button type="button" class="btn-notify-planner" onclick="notifyPlanner('{{ sekcja }}', '{{ linia }}')" style="display: inline-flex; align-items: center; gap: 8px; background: #f59e0b; color: #fff; border: 0; border-radius: 10px; padding: 10px 20px; font-weight: 700; cursor: pointer; box-shadow: 0 4px 12px rgba(245, 158, 11, 0.3);">
                    <span class="material-icons">send</span> POWIADOM PLANISTĘ
                </button>
            </div>
        </div>
        {% else %}
            {% set active_szarze_panel = namespace(rendered=false) %}
            {% set g_loop_idx = namespace(val=0) %}
            
            {# 1. Active orders (w toku) #}
            {% for p in plan if p[3]|lower == 'w toku' %}""" + correct_body + """
            {% endfor %}
            
            {# 2. Startable planned orders #}
            {% for p in plan if p[3]|lower == 'zaplanowane' and ((sekcja == 'Workowanie' and allowed_work_start_ids is defined and p[0] in allowed_work_start_ids) or (sekcja == 'Zasyp' and allowed_zasyp_start_ids is defined and p[0] in allowed_zasyp_start_ids)) %}""" + correct_body + """
            {% endfor %}
            
            {# 3. Other planned orders #}
            {% for p in plan if p[3]|lower == 'zaplanowane' and not ((sekcja == 'Workowanie' and allowed_work_start_ids is defined and p[0] in allowed_work_start_ids) or (sekcja == 'Zasyp' and allowed_zasyp_start_ids is defined and p[0] in allowed_zasyp_start_ids)) %}""" + correct_body + """
            {% endfor %}
            
            {# 4. Completed/other orders #}
            {% for p in plan if p[3]|lower not in ['w toku', 'zaplanowane'] %}""" + correct_body + """
            {% endfor %}
        {% endif %}
    </div>

""" + content[content.find('<!-- Modular Modal for Read-Only Plan Preview -->'):]

with open('templates/dashboard/_dashboard_production_list.html', 'w', encoding='utf-8') as f:
    f.write(new_content)
