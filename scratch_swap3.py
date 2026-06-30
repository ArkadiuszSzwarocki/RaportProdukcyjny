import re

with open("app/core/daemon.py", "r", encoding="utf-8") as f:
    content = f.read()

# Uncomment print logic
content = content.replace('''                                # ok_print, wrap_msg, printed_pallet_id = _print_wrapped_pallet_label_once(
                                #     plan_id,
                                #     last_printed_wrap_pallet_ids,
                                #     linia='AGRO',
                                # )
                                ok_print, wrap_msg, printed_pallet_id = False, "Wydruk po owijarce wyłączony na życzenie", None''',
                                '''                                ok_print, wrap_msg, printed_pallet_id = _print_wrapped_pallet_label_once(
                                    plan_id,
                                    last_printed_wrap_pallet_ids,
                                    linia='AGRO',
                                )''')

# Swap blocks
# Block 1 (wrap block)
wrap_block_start = "                        # Initialize wrapped baseline for new plans"
wrap_block_end = "                            plan_wrap_states[plan_id] = current_wrapped\n"

# Block 2 (counter block)
counter_block_start = "                        if current_pallet_cnt > 0:"
counter_block_end = "                                        _INSTANCE_ID,\n                                    )\n"

start1 = content.find(wrap_block_start)
end1 = content.find(wrap_block_end) + len(wrap_block_end)
block1 = content[start1:end1]

start2 = content.find(counter_block_start)
end2 = content.find(counter_block_end) + len(counter_block_end)
block2 = content[start2:end2]

new_content = content[:start1] + block2 + "                        \n" + block1 + content[end2:]

with open("app/core/daemon.py", "w", encoding="utf-8") as f:
    f.write(new_content)
print("done")
