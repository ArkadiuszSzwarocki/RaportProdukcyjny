import re

with open('templates/planista.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Define the correct block
correct_block = '''        html += '<div class="form-group"><label>Plan (kg):</label><input id="e_ton_' + id + '" name="tonaz" type="number" step="0.1" value="' + tonaz + '" required style="width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px;"></div>';
        html += '<div class="form-group"><label>Data planu:</label><input id="e_date_' + id + '" name="data_planu" type="date" value="{{ wybrana_data }}" style="width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px;"></div>';
        html += '<div class="form-group"><label>Data produkcji (opcjonalnie):</label><input id="e_prod_date_' + id + '" name="data_produkcji" type="date" value="' + dataProdukcji + '" style="width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px;"></div>';
        
        if (currentLinia.toLowerCase() === 'agro') {
            html += '<div class="form-group" style="grid-column: 1 / -1; z-index: 10;"><label style="font-weight: 600; color: #004d40;">Worek (wymagane):</label>';
            html += '<div class="searchable-select-wrapper" id="wrapper_e_opakowanie_' + id + '">';
            html += '  <span class="input-badge-indicator" id="e_opakowanie_indicator_' + id + '"></span>';
            html += '  <input type="text" id="e_opakowanie_search_' + id + '" class="searchable-select-input" placeholder="Wpisz lub wybierz worek..." autocomplete="off" style="width: 100%; padding: 8px 10px; border: 1px solid #ccc; border-radius: 4px;">';
            html += '  <input type="hidden" id="e_opakowanie_' + id + '" name="opakowanie_id">';
            html += '  <div id="e_opakowanie_dropdown_' + id + '" class="searchable-select-dropdown" style="display: none;"></div>';
            html += '</div></div>';

            html += '<div class="form-group" style="grid-column: 1 / -1; z-index: 9;"><label style="font-weight: 600; color: #4a148c;">Etykieta (wymagane):</label>';
            html += '<div class="searchable-select-wrapper" id="wrapper_e_etykieta_' + id + '">';
            html += '  <span class="input-badge-indicator" id="e_etykieta_indicator_' + id + '"></span>';
            html += '  <input type="text" id="e_etykieta_search_' + id + '" class="searchable-select-input" placeholder="Wpisz lub wybierz etykietê..." autocomplete="off" style="width: 100%; padding: 8px 10px; border: 1px solid #ccc; border-radius: 4px;">';
            html += '  <input type="hidden" id="e_etykieta_' + id + '" name="etykieta_id">';
            html += '  <div id="e_etykieta_dropdown_' + id + '" class="searchable-select-dropdown" style="display: none;"></div>';
            html += '</div></div>';
            
            // Add style to fix dropdown clipping in this popup
            html += '<style>#quickPopup, #quickPopup .qp-body { overflow: visible !important; }</style>';
        }

        html += '<div class="d-flex gap-10 mt-15" style="grid-column: 1 / -1; justify-content: flex-end; padding-top: 15px; border-top: 1px solid #e2e8f0;">';
        html += '  <button type="button" class="btn-action btn-success" onclick="submitEdit(' + id + ')">Zapisz</button>';
        html += '  <button type="button" class="btn-action btn-cancel" onclick="if(window.createQuickPopup && window.createQuickPopup._lastInst) window.createQuickPopup._lastInst.close()">Anuluj</button>';
        html += '</div>';
        html += '</form>';
        var popup = showQuickPopup('Edytuj zlecenie', html, { maxWidth: '1200px' });'''

# Find the start and end of the corrupted block
start_marker = "html += '<div class=\\"form-group\\"><label>Plan (kg):</label><input id=\\"e_ton_' + id + '\\" name=\\"tonaz\\""
end_marker = "var popup = showQuickPopup('Edytuj zlecenie', html, { maxWidth: '1200px' });"

start_idx = content.find(start_marker)
end_idx = content.find(end_marker, start_idx) + len(end_marker)

if start_idx != -1 and end_idx != -1:
    new_content = content[:start_idx] + correct_block + content[end_idx:]
    with open('templates/planista.html', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Fixed corrupted code successfully!")
else:
    print("Could not find markers.")
    print("Start:", start_idx)
    print("End:", end_idx)
