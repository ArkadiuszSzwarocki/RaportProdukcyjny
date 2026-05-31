import re

path = r'templates/reports/raport_zasypow.html'
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

# Replace the data-bs-toggle attributes with custom ones
html = html.replace('data-bs-toggle="collapse" data-bs-target="#details-{{ loop.index }}"', 
                    'class="raport-row-toggle" data-target="details-{{ loop.index }}"')

script = '''
<script>
document.addEventListener('DOMContentLoaded', function() {
    var toggleRows = document.querySelectorAll('tr.raport-row-toggle');
    toggleRows.forEach(function(row) {
        row.addEventListener('click', function(e) {
            var targetId = row.getAttribute('data-target');
            if (targetId) {
                var targetEl = document.getElementById(targetId);
                if (targetEl) {
                    var isHidden = targetEl.style.display === 'none' || targetEl.style.display === '' || targetEl.classList.contains('collapse');
                    if (isHidden) {
                        targetEl.style.display = 'block';
                        targetEl.classList.remove('collapse');
                        var icon = row.querySelector('.fa-chevron-down');
                        if (icon) {
                            icon.classList.remove('fa-chevron-down');
                            icon.classList.add('fa-chevron-up');
                        }
                    } else {
                        targetEl.style.display = 'none';
                        targetEl.classList.add('collapse');
                        var icon = row.querySelector('.fa-chevron-up');
                        if (icon) {
                            icon.classList.remove('fa-chevron-up');
                            icon.classList.add('fa-chevron-down');
                        }
                    }
                }
            }
        });
    });
});
</script>
{% endblock %}
'''

# Replace {% endblock %} with script + {% endblock %}
# Make sure we don't duplicate if it's already there
if 'document.addEventListener(\'DOMContentLoaded\', function() {' not in html:
    html = html.replace('{% endblock %}', script)

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)
print('Fixed HTML to use custom JS instead of Bootstrap attributes.')
