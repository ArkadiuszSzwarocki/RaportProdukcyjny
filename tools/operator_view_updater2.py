import codecs

path = 'a:/GitHub/RaportProdukcyjny/templates/includes/view_workowanie.html'
with codecs.open(path, 'r', encoding='utf-8') as f:
    code = f.read()

old_header = "<h3 class=\"header-title\">\u2699\ufe0f {{ _('odbior_palet') }}: {{ p[1] }} {% if p|length > 16 and p[16] == 'eksportowa' %}<span class=\"badge\" style=\"background-color: #f59e0b; color: white; margin-left: 10px;\">Eksport</span>{% endif %}</h3>"
new_header = "<h3 class=\"header-title\">\u2699\ufe0f {{ _('odbior_palet') }}: {{ p[1] }} {% if p|length > 29 and p[29] == 'eksportowa' %}<span class=\"badge\" style=\"background-color: #f59e0b; color: white; margin-left: 10px;\">Eksport</span>{% endif %}</h3>"
code = code.replace(old_header, new_header)

with codecs.open(path, 'w', encoding='utf-8') as f:
    f.write(code)
print("Updated view_workowanie.html again")
