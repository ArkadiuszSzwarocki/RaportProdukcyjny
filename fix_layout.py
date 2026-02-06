#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix layout.html JavaScript section"""

with open('templates/layout.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the section
start_marker = '        // Przełączanie widoczności menu języków'
end_marker = '    </script>'
start_idx = content.find(start_marker)

if start_idx != -1:
    # Find the real start (including blank line before)
    real_start = content.rfind('\n', 0, start_idx) + 1
    end_idx = content.find(end_marker, start_idx)
    
    if end_idx != -1:
        end_idx = content.find('\n', end_idx) + 1
        
        # Build new script section
        new_script = """
        function handleLogoError(img){
            try{
                if(img.src.indexOf('agro_logo.png') !== -1){
                    img.src = '{{ url_for("static", filename="logo.png") }}';
                } else {
                    img.onerror = null;
                    img.src = 'https://agronetzwerk.de/wp-content/uploads/2021/04/Agronetzwerk-Logo.png';
                }
            }catch(e){
                img.onerror = null;
            }
        }
        
        // Przełączanie widoczności menu języków
        function toggleLanguageMenu(){
            const menu = document.getElementById('languageMenu');
            if(menu) {
                menu.style.display = menu.style.display === 'none' ? 'flex' : 'none';
            }
        }
        
        // Zamykanie menu ponad innymi klikami w dokumencie
        document.addEventListener('click', function(event) {
            const selector = document.querySelector('.language-selector');
            const menu = document.getElementById('languageMenu');
            if(selector && menu && !selector.contains(event.target)) {
                menu.style.display = 'none';
            }
        });
        
        // Przełączanie języka aplikacji
        function switchLanguage(lang){
            fetch('/api/set_language', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({language: lang})
            })
            .then(r => r.json())
            .then(data => {
                if(data.success){
                    const langNames = {uk: 'Українску', pl: 'Polski', en: 'English'};
                    showToast('✓ Język zmieniony na ' + (langNames[lang] || lang), 'success');
                    setTimeout(() => location.reload(), 500);
                } else {
                    showToast('❌ ' + (data.message || 'Błąd zmiany języka'), 'error');
                }
            })
            .catch(err => {
                showToast('❌ Błąd: ' + err.message, 'error');
            });
        }
    </script>"""
        
        new_content = content[:real_start] + new_script + '\n' + content[end_idx:]
        
        with open('templates/layout.html', 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print('✓ File cleaned and fixed successfully')
    else:
        print('❌ Could not find end marker')
else:
    print('❌ Could not find start marker')
