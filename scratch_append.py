import os

content = open('templates/agro_warehouse/index.html', encoding='utf-8').read()
lines = content.split('\n')

for i, l in enumerate(lines):
    if '{% for s in inventory %}' in l and 'agro-inventory-list' in lines[i-1]:
        start_loop = i
        break

for i in range(start_loop+1, len(lines)):
    if '{% endfor %}' in lines[i]:
        if '</div>' in lines[i+1]:
            end_loop = i
            break

part2 = '''        {% else %}
            <div style="padding: 20px; text-align: center; color: #64748b; font-size: 15px; background: #fff; border-radius: 12px; border: 1px solid #e2e8f0;">
                Brak surowców na stanie dla wybranej linii.
            </div>
        {% endfor %}'''

lines[end_loop] = part2
open('templates/agro_warehouse/index.html', 'w', encoding='utf-8').write('\n'.join(lines))
print('Added {% else %}')
