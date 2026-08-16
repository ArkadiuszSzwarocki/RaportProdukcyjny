# -*- coding: utf-8 -*-
import os

filepath = 'a:/GitHub/RaportProdukcyjny/static/scripts.js'
with open(filepath, 'r', encoding='cp1250') as f:
    content = f.read()

target = """        if (planId) {
            url += '&plan_id=' + encodeURIComponent(planId);
        }
        const fetchOptions = {
            method: 'POST',"""

replacement = """        if (planId) {
            url += '&plan_id=' + encodeURIComponent(planId);
        }
        
        const prefIp = localStorage.getItem('agromes_preferred_zpl_printer');
        const prefName = localStorage.getItem('agromes_preferred_zpl_printer_name');
        if (prefIp) url += '&printer_ip=' + encodeURIComponent(prefIp.replace('net:', ''));
        if (prefName) url += '&printer_name=' + encodeURIComponent(prefName);

        const fetchOptions = {
            method: 'POST',"""

if target in content:
    content = content.replace(target, replacement)
    print("Successfully updated drukujZPLDirect.")
else:
    print("Target not found.")

modal_logic = """

// Printer settings modal logic
window.openPrinterSettingsModal = function() {
    let modal = document.getElementById('printer-settings-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'printer-settings-modal';
        modal.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;z-index:9999;';
        modal.innerHTML = `
            <div style="background:#fff;padding:20px;border-radius:8px;width:90%;max-width:400px;box-shadow:0 4px 6px rgba(0,0,0,0.1);">
                <h3 style="margin-top:0;margin-bottom:15px;font-size:1.2rem;display:flex;align-items:center;gap:8px;">
                    <span class="material-icons">print</span> Ustawienia drukarki ZPL
                </h3>
                <div style="margin-bottom:15px;">
                    <label style="display:block;margin-bottom:5px;font-weight:500;">Wybierz drukarkê docelow¹:</label>
                    <select id="printer-select" class="input-modern w-100" style="padding:8px;border:1px solid #ccc;border-radius:4px;">
                        <option value="">Wczytywanie...</option>
                    </select>
                </div>
                <div style="display:flex;justify-content:flex-end;gap:10px;">
                    <button type="button" class="btn-action btn-outline-secondary" onclick="document.getElementById('printer-settings-modal').style.display='none'">Anuluj</button>
                    <button type="button" class="btn-action btn-blue" onclick="savePrinterSelection()">Zapisz</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    }
    
    modal.style.display = 'flex';
    
    // Fetch printers
    fetch('/magazyn-dostawy/api/active-printers')
        .then(r => r.json())
        .then(data => {
            const select = document.getElementById('printer-select');
            select.innerHTML = '<option value="">(domyœlna)</option>';
            if (data.success && data.printers) {
                data.printers.forEach(p => {
                    const opt = document.createElement('option');
                    opt.value = p.selection_value;
                    opt.textContent = p.nazwa + (p.ip ? ' (' + p.ip + ')' : '');
                    opt.dataset.ip = p.ip || '';
                    opt.dataset.name = p.nazwa || '';
                    select.appendChild(opt);
                });
                
                const pref = localStorage.getItem('agromes_preferred_zpl_printer');
                if (pref) {
                    select.value = pref;
                }
            }
        })
        .catch(err => {
            console.error('Error fetching printers:', err);
            document.getElementById('printer-select').innerHTML = '<option value="">B³¹d ³adowania</option>';
        });
};

window.savePrinterSelection = function() {
    const select = document.getElementById('printer-select');
    const selected = select.options[select.selectedIndex];
    
    if (selected && selected.value) {
        localStorage.setItem('agromes_preferred_zpl_printer', selected.value);
        localStorage.setItem('agromes_preferred_zpl_printer_name', selected.dataset.name);
        if (typeof showToast === 'function') showToast('Drukarka ustawiona: ' + selected.dataset.name, 'success');
    } else {
        localStorage.removeItem('agromes_preferred_zpl_printer');
        localStorage.removeItem('agromes_preferred_zpl_printer_name');
        if (typeof showToast === 'function') showToast('Przywrócono domyœln¹ drukarkê', 'info');
    }
    
    document.getElementById('printer-settings-modal').style.display = 'none';
};

window.workowaniePopulatePrinter = function(form) {
    const prefIp = localStorage.getItem('agromes_preferred_zpl_printer');
    const prefName = localStorage.getItem('agromes_preferred_zpl_printer_name');
    if (prefIp && form.querySelector('.workowanie-printer-ip')) {
        form.querySelector('.workowanie-printer-ip').value = prefIp.replace('net:', '');
    }
    if (prefName && form.querySelector('.workowanie-printer-name')) {
        form.querySelector('.workowanie-printer-name').value = prefName;
    }
};
"""

if "window.openPrinterSettingsModal" not in content:
    content += modal_logic
    print("Added modal logic.")
else:
    print("Modal logic already present.")

with open(filepath, 'w', encoding='cp1250') as f:
    f.write(content)

