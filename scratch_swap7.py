import sys

with open('app/core/daemon.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Verify the lines to ensure safety
assert '# Initialize wrapped baseline' in lines[677]
assert 'plan_wrap_states[plan_id] = current_wrapped' in lines[710]
assert 'if current_pallet_cnt > 0:' in lines[712]

wrap_block = lines[677:712]  # from 677 to 711 inclusive
del lines[677:712]

# find where to insert. The line we want to insert before is:
# '                    else:\n' which was at 845.
insert_idx = -1
for i, line in enumerate(lines):
    if line == '                    else:\n' and '# No active plan' in lines[i+1]:
        insert_idx = i
        break

assert insert_idx != -1

lines = lines[:insert_idx] + wrap_block + lines[insert_idx:]

new_content = "".join(lines)

new_content = new_content.replace(
'''                                # ok_print, wrap_msg, printed_pallet_id = _print_wrapped_pallet_label_once(
                                #     plan_id,
                                #     last_printed_wrap_pallet_ids,
                                #     linia='AGRO',
                                # )
                                ok_print, wrap_msg, printed_pallet_id = False, "Wydruk po owijarce wyłączony na życzenie", None''',
'''                                ok_print, wrap_msg, printed_pallet_id = _print_wrapped_pallet_label_once(
                                    plan_id,
                                    last_printed_wrap_pallet_ids,
                                    linia='AGRO',
                                )'''
)

with open('app/core/daemon.py', 'w', encoding='utf-8') as f:
    f.write(new_content)
print("Done swapping lines safely.")
