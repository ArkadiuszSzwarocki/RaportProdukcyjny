import base64

content_b64 = b'''Ly8gUHJpbnRlciBzZXR0aW5ncyBtb2RhbCBsb2dpYwp3aW5kb3cub3BlblByaW50ZXJTZXR0aW5n
c01vZGFsID0gZnVuY3Rpb24oKSB7CiAgICBsZXQgbW9kYWwgPSBkb2N1bWVudC5nZXRFbGVtZW50
QnlJZCgncHJpbnRlci1zZXR0aW5ncy1tb2RhbCcpOwogICAgaWYgKCFtb2RhbCkgewogICAgICAg
IG1vZGFsID0gZG9jdW1lbnQuY3JlYXRlRWxlbWVudCgndmlldy1wcmludGVyLW1vZGFsJyk7CiAg
ICAgICAgbW9kYWwuaWQgPSAncHJpbnRlci1zZXR0aW5ncy1tb2RhbCc7CiAgICAgICAgbW9kYWwu
c3R5bGUuY3NzVGV4dCA9ICdwb3NpdGlvbjpmaXhlZDt0b3A6MDtsZWZ0OjA7d2lkdGg6MTAwJTto
ZWlnaHQ6MTAwJTtiYWNrZ3JvdW5kOnJnYmEoMCwwLDAsMC41KTtkaXNwbGF5OmZsZXg7YWxpZ24t
aXRlbXM6Y2VudGVyO2p1c3RpZnktY29udGVudDpjZW50ZXI7ei1pbmRleDo5OTk5Oyc7CiAgICAg
ICAgbW9kYWwuaW5uZXJIVE1MID0gYAogICAgICAgICAgICA8ZGl2IHN0eWxlPSJiYWNrZ3JvdW5k
OiNmZmY7cGFkZGluZzoyMHB4O2JvcmRlci1yYWRpdXM6OHB4O3dpZHRoOjkwJTttYXgtd2lkdGg6
NDAwcHg7Ym94LXNoYWRvdzowIDRweCA2cHggcmdiYSgwLDAsMCwwLjEpOyI+CiAgICAgICAgICAg
ICAgICA8aDMgc3R5bGU9Im1hcmdpbi10b3A6MDttYXJnaW4tYm90dG9tOjE1cHg7Zm9udC1zaXpl
OjEuMnJlbTtkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDo4cHg7Ij4KICAgICAg
ICAgICAgICAgICAgICA8c3BhbiBjbGFzcz0ibWF0ZXJpYWwtaWNvbnMiPnByaW50PC9zcGFuPiBV
c3Rhd2llbmlhIGRydWthcmtpIFpQTAogICAgICAgICAgICAgICAgPC9oMz4KICAgICAgICAgICAg
ICAgIDxkaXYgc3R5bGU9Im1hcmdpbi1ib3R0b206MTVweDsiPgogICAgICAgICAgICAgICAgICAg
IDxsYWJlbCBzdHlsZT0iZGlzcGxheTpibG9jazttYXJnaW4tYm90dG9tOjVweDtmb250LXdlaWdo
dDo1MDA7Ij5XeWJpZXJ6IGRydWthcmvEmSBkb2NlbG93xIU6PC9sYWJlbD4KICAgICAgICAgICAg
ICAgICAgICA8c2VsZWN0IGlkPSJwcmludGVyLXNlbGVjdCIgY2xhc3M9ImlucHV0LW1vZGVybiB3
LTEwMCIgc3R5bGU9InBhZGRpbmc6OHB4O2JvcmRlcjoxcHggc29saWQgI2NjYztib3JkZXItcmFk
aXVzOjRweDsiPgogICAgICAgICAgICAgICAgICAgICAgICA8b3B0aW9uIHZhbHVlPSIiPldjenl0
eXdhbmllLi4uPC9vcHRpb24+CiAgICAgICAgICAgICAgICAgICAgPC9zZWxlY3Q+CiAgICAgICAg
ICAgICAgICA8L2Rpdj4KICAgICAgICAgICAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6ZmxleDtq
dXN0aWZ5LWNvbnRlbnQ6ZmxleC1lbmQ7Z2FwOjEwcHg7Ij4KICAgICAgICAgICAgICAgICAgICA8
YnV0dG9uIHR5cGU9ImJ1dHRvbiIgY2xhc3M9ImJ0bi1hY3Rpb24gYnRuLW91dGxpbmUtc2Vjb25k
YXJ5IiBvbmNsaWNrPSJkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncHJpbnRlci1zZXR0aW5ncy1t
b2RhbCcpLnN0eWxlLmRpc3BsYXk9J25vbmUnIj5BbnVsdWo8L2J1dHRvbj4KICAgICAgICAgICAg
ICAgICAgICA8YnV0dG9uIHR5cGU9ImJ1dHRvbiIgY2xhc3M9ImJ0bi1hY3Rpb24gYnRuLWJsdWUi
IG9uY2xpY2s9InNhdmVQcmludGVyU2VsZWN0aW9uKCkiPlphcGlzejwvYnV0dG9uPgogICAgICAg
ICAgICAgICAgPC9kaXY+CiAgICAgICAgICAgIDwvZGl2PgogICAgICAgIGA7CiAgICAgICAgZG9j
dW1lbnQuYm9keS5hcHBlbmRDaGlsZChtb2RhbCk7CiAgICB9CiAgICAKICAgIG1vZGFsLnN0eWxl
LmRpc3BsYXkgPSAnZmxleCc7CiAgICAKICAgIC8vIEZldGNoIHByaW50ZXJzCiAgICBmZXRjaCgn
L21hZ2F6eW4tZG9zdGF3eS9hcGkvYWN0aXZlLXByaW50ZXJzJykKICAgICAgICAudGhlbihyID0+
IHIuanNvbigpKQogICAgICAgIC50aGVuKGRhdGEgPT4gewogICAgICAgICAgICBjb25zdCBzZWxl
Y3QgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncHJpbnRlci1zZWxlY3QnKTwKICAgICAgICAg
ICAgc2VsZWN0LmlubmVySFRNTCA9ICc8b3B0aW9uIHZhbHVlPSIiPihkb215xZtsbmEpPC9vcHRp
b24+JzsKICAgICAgICAgICAgaWYgKGRhdGEuc3VjY2VzcyAmJiBkYXRhLnByaW50ZXJzKSB7CiAg
ICAgICAgICAgICAgICBkYXRhLnByaW50ZXJzLmZvckVhY2gocCA9PiB7CiAgICAgICAgICAgICAg
ICAgICAgY29uc3Qgb3B0ID0gZG9jdW1lbnQuY3JlYXRlRWxlbWVudCgnb3B0aW9uJyk7CiAgICAg
ICAgICAgICAgICAgICAgb3B0LnZhbHVlID0gcC5zZWxlY3Rpb25fdmFsdWU7CiAgICAgICAgICAg
ICAgICAgICAgb3B0LnRleHRDb250ZW50ID0gcC5uYXp3YSArIChwLmlwID8gJyAoJyArIHAuaXAg
KyAnKScgOiAnJyk7CiAgICAgICAgICAgICAgICAgICAgb3B0LmRhdGFzZXQuaXAgPSBwLmlwIHx8
ICcnOwogICAgICAgICAgICAgICAgICAgIG9wdC5kYXRhc2V0Lm5hbWUgPSBwLm5hendhIHx8ICcn
OwogICAgICAgICAgICAgICAgICAgIHNlbGVjdC5hcHBlbmRDaGlsZChvcHQpOwogICAgICAgICAg
ICAgICAgfSk7CiAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgIGNvbnN0IHByZWYgPSBs
b2NhbFN0b3JhZ2UuZ2V0SXRlbSgnYWdyb21lc19wcmVmZXJyZWRfenBsX3ByaW50ZXInKTsKICAg
ICAgICAgICAgICAgIGlmIChwcmVmKSB7CiAgICAgICAgICAgICAgICAgICAgc2VsZWN0LnZhbHVl
ID0gcHJlZjsKICAgICAgICAgICAgICAgIH0KICAgICAgICAgICAgfQogICAgICAgIH0pCiAgICAg
ICAgLmNhdGNoKGVyciA9PiB7CiAgICAgICAgICAgIGNvbnNvbGUuZXJyb3IoJ0Vycm9yIGZldGNo
aW5nIHByaW50ZXJzOicsIGVycik7CiAgICAgICAgICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlk
KCdwcmludGVyLXNlbGVjdCcpLmlubmVySFRNTCA9ICc8b3B0aW9uIHZhbHVlPSIiPkLFgsSFZCDF
gmFkb3dhbmlhPC9vcHRpb24+JzsKICAgICAgICB9KTsKfTsKCndpbmRvdy5zYXZlUHJpbnRlclNl
bGVjdGlvbiA9IGZ1bmN0aW9uKCkgewogICAgY29uc3Qgc2VsZWN0ID0gZG9jdW1lbnQuZ2V0RWxl
bWVudEJ5SWQoJ3ByaW50ZXItc2VsZWN0Jyk7CiAgICBjb25zdCBzZWxlY3RlZCA9IHNlbGVjdC5v
cHRpb25zW3NlbGVjdC5zZWxlY3RlZEluZGV4XTsKICAgIAogICAgaWYgKHNlbGVjdGVkICYmIHNl
bGVjdGVkLnZhbHVlKSB7CiAgICAgICAgbG9jYWxTdG9yYWdlLnNldEl0ZW0oJ2Fncm9tZXNfcHJl
ZmVycmVkX3pwbF9wcmludGVyJywgc2VsZWN0ZWQudmFsdWUpOwogICAgICAgIGxvY2FsU3RvcmFn
ZS5zZXRJdGVtKCdhZ3JvbWVzX3ByZWZlcnJlZF96cGxfcHJpbnRlcl9uYW1lJywgc2VsZWN0ZWQu
ZGF0YXNldC5uYW1lKTsKICAgICAgICBpZiAodHlwZW9mIHNob3dUb2FzdCA9PT0gJ2Z1bmN0aW9u
Jykgc2hvd1RvYXN0KCdEcnVrYXJrYSB1c3Rhd2lvbmE6ICcgKyBzZWxlY3RlZC5kYXRhc2V0Lm5h
bWUsICdzdWNjZXNzJyk7CiAgICB9IGVsc2UgewogICAgICAgIGxvY2FsU3RvcmFnZS5yZW1vdmVJ
dGVtKCdhZ3JvbWVzX3ByZWZlcnJlZF96cGxfcHJpbnRlcicpOwogICAgICAgIGxvY2FsU3RvcmFn
ZS5yZW1vdmVJdGVtKCdhZ3JvbWVzX3ByZWZlcnJlZF96cGxfcHJpbnRlcl9uYW1lJyk7CiAgICAg
ICAgaWYgKHR5cGVvZiBzaG93VG9hc3QgPT09ICdmdW5jdGlvbicpIHNob3dUb2FzdCgnUHJ6eXdy
w7Njb25vIGRvbXnFm2xuxIUgZHJ1a2Fya8SZJywgJ2luZm8nKTsKICAgIH0KICAgIAogICAgZG9j
dW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3ByaW50ZXItc2VsZWN0LW1vZGFsJykuc3R5bGUuZGlzcGxh
eSA9ICdub25lJzsKfTsKCndpbmRvdy53b3Jrb3dhbmllUG9wdWxhdGVQcmludGVyID0gZnVuY3Rp
b24oZm9ybSkgewogICAgY29uc3QgcHJlZklwID0gbG9jYWxTdG9yYWdlLmdldEl0ZW0oJ2Fncm9t
ZXNfcHJlZmVycmVkX3pwbF9wcmludGVyJyk7CiAgICBjb25zdCBwcmVmTmFtZSA9IGxvY2FsU3Rv
cmFnZS5nZXRJdGVtKCdhZ3JvbWVzX3ByZWZlcnJlZF96cGxfcHJpbnRlcl9uYW1lJyk7CiAgICBp
ZiAocHJlZklwICYmIGZvcm0ucXVlcnlTZWxlY3RvcignLndvcmtvd2FuaWUtcHJpbnRlci1pcCcp
KSB7CiAgICAgICAgZm9ybS5xdWVyeVNlbGVjdG9yKCcud29ya293YW5pZS1wcmludGVyLWlwJyku
dmFsdWUgPSBwcmVmSXAucmVwbGFjZSgnbmV0OicsICcnKTsKICAgIH0KICAgIGlmIChwcmVmTmFt
ZSAmJiBmb3JtLnF1ZXJ5U2VsZWN0b3IoJy53b3Jrb3dhbmllLXByaW50ZXItbmFtZScpKSB7CiAg
ICAgICAgZm9ybS5xdWVyeVNlbGVjdG9yKCcud29ya293YW5pZS1wcmludGVyLW5hbWUnKS52YWx1
ZSA9IHByZWZOYW1lOwogICAgfQp9Ow=='''

filepath = 'a:/GitHub/RaportProdukcyjny/static/scripts.js'
with open(filepath, 'rb') as f:
    content = f.read()

target = b'''        if (planId) {
            url += '&plan_id=' + encodeURIComponent(planId);
        }
        const fetchOptions = {
            method: 'POST','''

replacement = b'''        if (planId) {
            url += '&plan_id=' + encodeURIComponent(planId);
        }
        
        const prefIp = localStorage.getItem('agromes_preferred_zpl_printer');
        const prefName = localStorage.getItem('agromes_preferred_zpl_printer_name');
        if (prefIp) url += '&printer_ip=' + encodeURIComponent(prefIp.replace('net:', ''));
        if (prefName) url += '&printer_name=' + encodeURIComponent(prefName);

        const fetchOptions = {
            method: 'POST','''

if target in content:
    content = content.replace(target, replacement)
    print("Replaced target.")
else:
    target2 = b'''        if (planId) {\r\n            url += '&plan_id=' + encodeURIComponent(planId);\r\n        }\r\n        const fetchOptions = {\r\n            method: 'POST','''
    replacement2 = b'''        if (planId) {\r\n            url += '&plan_id=' + encodeURIComponent(planId);\r\n        }\r\n        \r\n        const prefIp = localStorage.getItem('agromes_preferred_zpl_printer');\r\n        const prefName = localStorage.getItem('agromes_preferred_zpl_printer_name');\r\n        if (prefIp) url += '&printer_ip=' + encodeURIComponent(prefIp.replace('net:', ''));\r\n        if (prefName) url += '&printer_name=' + encodeURIComponent(prefName);\r\n\r\n        const fetchOptions = {\r\n            method: 'POST','''
    if target2 in content:
        content = content.replace(target2, replacement2)
        print("Replaced target (CRLF).")
    else:
        print("Target not found.")

modal_str = base64.b64decode(content_b64)
if b'window.openPrinterSettingsModal' not in content:
    content += b'\r\n' + modal_str
    print("Appended modal logic.")

with open(filepath, 'wb') as f:
    f.write(content)
print("Done.")
