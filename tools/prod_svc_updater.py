import codecs

path = 'a:/GitHub/RaportProdukcyjny/app/services/production_service.py'
with codecs.open(path, 'r', encoding='utf-8') as f:
    code = f.read()

old_block = """            # Extract opakowanie_nazwa and etykieta_nazwa if present
            opak_nazwa = p[15] if len(p) > 15 else None
            etyk_nazwa = p[16] if len(p) > 16 else None
            
            # Shrink back to 15 items to not mess up fixed index assignments
            while len(p) > 15:
                p.pop()

            # Ensure we have enough space for extra metadata (indices 15+)
            while len(p) < 29:
                p.append(None)
                
            p[27] = opak_nazwa
            p[28] = etyk_nazwa"""

new_block = """            # The columns are: data_planu(13), zasyp_id(14), odrzuty(15), rodzaj_palety(16), opak(17), etyk(18)
            odrzuty = p[15] if len(p) > 15 else 0
            rodzaj_pal = p[16] if len(p) > 16 else 'krajowa'
            opak_nazwa = p[17] if len(p) > 17 else None
            etyk_nazwa = p[18] if len(p) > 18 else None
            
            # Shrink back to 15 items
            while len(p) > 15:
                p.pop()

            # Ensure we have enough space for extra metadata
            while len(p) < 31:
                p.append(None)
                
            p[27] = opak_nazwa
            p[28] = etyk_nazwa
            p[29] = rodzaj_pal
            p[30] = odrzuty"""

code = code.replace(old_block, new_block)

with codecs.open(path, 'w', encoding='utf-8') as f:
    f.write(code)
print("Updated production_service.py")
