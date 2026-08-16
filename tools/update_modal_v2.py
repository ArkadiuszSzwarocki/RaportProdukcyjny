import os

file_path = 'a:/GitHub/RaportProdukcyjny/templates/ustawienia_index.html'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the HTML containers
container_term_start = content.find('<!-- Terminal Emulator -->')
container_term_end = content.find('</div>', content.find('<div id="verify-terminal-lines"></div>')) + 6
if container_term_start != -1 and container_term_end != -1:
    content = content[:container_term_start] + '<!-- Terminal results will open in modal -->' + content[container_term_end:]

container_db_start = content.find('<!-- DB Stats Table Grid -->')
container_db_end = content.find('</div>', content.find('<tbody id="db-stats-tbody"></tbody>')) + 6
if container_db_start != -1 and container_db_end != -1:
    content = content[:container_db_start] + '<!-- DB Stats results will open in modal -->' + content[container_db_end:]

modal_html = '''
<!-- Master Admin Large Modal -->
<div id="master-large-modal" style="display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 9999; align-items: center; justify-content: center; backdrop-filter: blur(5px);">
    <div style="background: #ffffff; width: 90%; max-width: 1000px; height: 85%; max-height: 800px; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); display: flex; flex-direction: column; overflow: hidden; position: relative;">
        <!-- Modal Header -->
        <div style="background: #1e293b; color: white; padding: 15px 20px; display: flex; justify-content: space-between; align-items: center;">
            <h3 id="master-modal-title" style="margin: 0; font-size: 1.2rem; font-weight: 700; display: flex; align-items: center; gap: 10px;">
                <span class="material-icons">terminal</span> Wynik operacji
            </h3>
            <button type="button" onclick="document.getElementById('master-large-modal').style.display='none'" style="background: transparent; border: none; color: white; cursor: pointer; display: flex; align-items: center; padding: 5px; border-radius: 5px;" onmouseover="this.style.background='rgba(255,255,255,0.1)'" onmouseout="this.style.background='transparent'">
                <span class="material-icons">close</span>
            </button>
        </div>
        <!-- Modal Body -->
        <div id="master-modal-body" style="padding: 20px; overflow-y: auto; flex-grow: 1; background: #f8fafc;">
        </div>
    </div>
</div>
'''

# Insert modal HTML just before the closing {% endblock %}
endblock_idx = content.find('{% endblock %}')
if endblock_idx != -1 and 'id="master-large-modal"' not in content:
    content = content[:endblock_idx] + modal_html + '\n' + content[endblock_idx:]

new_js = '''// MasterAdmin System Verification
        async function runSystemVerification() {
            const btn = document.getElementById('btn-run-verify');
            const modal = document.getElementById('master-large-modal');
            const modalBody = document.getElementById('master-modal-body');
            const modalTitle = document.getElementById('master-modal-title');

            modalTitle.innerHTML = '<span class="material-icons">health_and_safety</span> Weryfikacja systemu (Error Trap)';
            modalBody.innerHTML = '<div style="background: #0f172a; color: #38bdf8; padding: 20px; font-family: monospace; border-radius: 8px; min-height: 100%; font-size: 1.1rem;"><div id="verify-modal-lines" style="color: #888;">> Inicjalizacja testów integralności...</div></div>';
            modal.style.display = 'flex';
            
            btn.disabled = true;
            btn.textContent = 'Testowanie...';

            try {
                const resp = await fetch('/admin/master/verify');
                const data = await resp.json();

                const lines = data.output.split('\\n');
                const linesContainer = document.getElementById('verify-modal-lines');
                linesContainer.innerHTML = '';

                let idx = 0;
                function printNextLine() {
                    if (idx < lines.length) {
                        const line = lines[idx];
                        if (line.trim()) {
                            let color = '#ffc107';
                            if (line.includes('[OK]') || line.includes('[SUCCESS]')) color = '#32cd32';
                            if (line.includes('[SYNTAX ERROR]') || line.includes('[CRITICAL ERROR]') || line.includes('[FAILED]')) color = '#ef4444';
                            
                            const div = document.createElement('div');
                            div.style.color = color;
                            div.style.marginBottom = '4px';
                            div.textContent = line;
                            linesContainer.appendChild(div);
                            
                            // auto scroll
                            modalBody.scrollTop = modalBody.scrollHeight;
                        }
                        idx++;
                        setTimeout(printNextLine, 10);
                    } else {
                        btn.disabled = false;
                        btn.textContent = 'Uruchom testy';
                        const div = document.createElement('div');
                        div.style.color = '#38bdf8';
                        div.style.marginTop = '15px';
                        div.style.fontWeight = 'bold';
                        div.textContent = '> Weryfikacja zakończona.';
                        linesContainer.appendChild(div);
                        modalBody.scrollTop = modalBody.scrollHeight;
                    }
                }
                printNextLine();

            } catch (err) {
                document.getElementById('verify-modal-lines').innerHTML = '<div style="color: red;">Błąd sieci lub serwera: ' + err.message + '</div>';
                btn.disabled = false;
                btn.textContent = 'Uruchom testy';
            }
        }

        // MasterAdmin DB Statistics Loader
        async function loadDbStats() {
            const btn = document.getElementById('btn-run-db-stats');
            const modal = document.getElementById('master-large-modal');
            const modalBody = document.getElementById('master-modal-body');
            const modalTitle = document.getElementById('master-modal-title');

            modalTitle.innerHTML = '<span class="material-icons">storage</span> Statystyki Bazy Danych';
            modalBody.innerHTML = '<div style="text-align: center; padding: 80px; color: #64748b; font-size: 1.2rem;"><span class="material-icons" style="font-size: 4rem; display: block; margin-bottom: 20px; animation: pulse-amber 1.5s infinite;">hourglass_empty</span> Analizowanie baz danych...</div>';
            modal.style.display = 'flex';

            btn.disabled = true;
            btn.textContent = 'Analizowanie...';

            try {
                const resp = await fetch('/admin/master/db-stats');
                const data = await resp.json();

                if (data.success) {
                    let tableHtml = `
                    <div style="background: white; border-radius: 8px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
                        <table style="width: 100%; border-collapse: collapse; text-align: left;">
                            <thead style="background: #f8fafc; border-bottom: 2px solid #cbd5e1;">
                                <tr>
                                    <th style="padding: 16px 20px; font-weight: 700; color: #334155; font-size: 1.1rem;">Tabela</th>
                                    <th style="padding: 16px 20px; font-weight: 700; color: #334155; text-align: right; font-size: 1.1rem;">Wiersze (Rekordy)</th>
                                    <th style="padding: 16px 20px; font-weight: 700; color: #334155; text-align: right; font-size: 1.1rem;">Zajętość dysku (MB)</th>
                                </tr>
                            </thead>
                            <tbody>
                    `;

                    if (data.stats && data.stats.length > 0) {
                        data.stats.forEach((stat, i) => {
                            let nameColor = '#0f172a';
                            let rowBg = i % 2 === 0 ? '#ffffff' : '#f8fafc';
                            let warningIcon = '';

                            if (stat.rows > 10000 || stat.size_mb > 5.0) {
                                nameColor = '#d97706';
                                warningIcon = '<span class="material-icons" style="font-size: 18px; vertical-align: middle; margin-right: 8px; color: #d97706;">warning</span>';
                                rowBg = '#fffbeb';
                            }

                            tableHtml += `
                                <tr style="border-bottom: 1px solid #e2e8f0; background: ${rowBg}; transition: background 0.2s;" onmouseover="this.style.background='#f1f5f9'" onmouseout="this.style.background='${rowBg}'">
                                    <td style="padding: 16px 20px; color: ${nameColor}; font-weight: 500; font-family: monospace; font-size: 1.1rem;">
                                        ${warningIcon}${stat.name}
                                    </td>
                                    <td style="padding: 16px 20px; text-align: right; color: #475569; font-weight: 600; font-size: 1.1rem;">
                                        ${stat.rows.toLocaleString('pl-PL')}
                                    </td>
                                    <td style="padding: 16px 20px; text-align: right; color: #475569; font-weight: 600; font-size: 1.1rem;">
                                        <span style="background: #e0f2fe; color: #0369a1; padding: 4px 10px; border-radius: 12px;">${stat.size_mb} MB</span>
                                    </td>
                                </tr>
                            `;
                        });
                    } else {
                        tableHtml += '<tr><td colspan="3" style="text-align: center; padding: 30px; color: #94a3b8; font-size: 1.1rem;">Brak danych do wyświetlenia.</td></tr>';
                    }

                    tableHtml += `
                            </tbody>
                        </table>
                    </div>
                    `;
                    modalBody.innerHTML = tableHtml;
                } else {
                    modalBody.innerHTML = '<div style="color: #ef4444; padding: 20px; text-align: center; font-size: 1.2rem;">Błąd: ' + (data.message || 'Nieznany błąd') + '</div>';
                }
            } catch (err) {
                modalBody.innerHTML = '<div style="color: #ef4444; padding: 20px; text-align: center; font-size: 1.2rem;">Błąd sieci: ' + err.message + '</div>';
            } finally {
                btn.disabled = false;
                btn.textContent = 'Analizuj DB';
            }
        }
'''

js_start = content.find('// MasterAdmin System Verification')
js_end = content.find('// Check on load', js_start)

if js_start != -1 and js_end != -1:
    content = content[:js_start] + new_js + '\n        ' + content[js_end:]

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("SUCCESS")
