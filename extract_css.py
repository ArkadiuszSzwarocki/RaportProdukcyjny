with open('a:/GitHub/RaportProdukcyjny/templates/agro_folio_rozliczenie.html', 'r', encoding='utf-8') as f:
    content = f.read()

import re

# We just need to extract from '<!-- Historia rolek -->' to '{% endif %}{# end if active_plan #}'
match = re.search(r'(<!-- Historia rolek -->.*?)(?={% endif %}{# end if active_plan #})', content, re.DOTALL)
if match:
    with open('a:/GitHub/RaportProdukcyjny/templates/agro/components/_folio_history_table.html', 'w', encoding='utf-8') as f:
        f.write(match.group(1))

# Now replace the main file:
new_content = re.sub(
    r'(<!-- Summary Cards -->.*?)(?={% endif %}{# end if active_plan #})',
    '''
    {% include 'agro/components/_folio_simulator.html' %}
    {% include 'agro/components/_folio_summary.html' %}
    {% include 'agro/components/_folio_add_form.html' %}
    {% include 'agro/components/_folio_active_rolls.html' %}
    {% include 'agro/components/_folio_history_table.html' %}
    ''',
    content,
    flags=re.DOTALL
)

# And extract CSS
css_match = re.search(r'<style>(.*?)</style>', new_content, re.DOTALL)
if css_match:
    with open('a:/GitHub/RaportProdukcyjny/static/css/agro_folio.css', 'w', encoding='utf-8') as out:
        out.write(css_match.group(1).strip())

    new_content = re.sub(
        r'{% block extra_css %}.*?{% endblock %}',
        '''{% block extra_css %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/agro_folio.css') }}">
{% endblock %}''',
        new_content,
        flags=re.DOTALL
    )

with open('a:/GitHub/RaportProdukcyjny/templates/agro_folio_rozliczenie.html', 'w', encoding='utf-8') as f:
    f.write(new_content)
print("Done!")
