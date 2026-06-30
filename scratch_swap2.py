import re

with open("app/core/daemon.py", "r", encoding="utf-8") as f:
    content = f.read()

# Define the start and end of the wrap block
wrap_start_str = "                        # Initialize wrapped baseline for new plans, then only print on False->True transitions."
wrap_end_str = "                            plan_wrap_states[plan_id] = current_wrapped\n"

# Define the start and end of the counter block
counter_start_str = "                        if current_pallet_cnt > 0:"
counter_end_str = "                                    )\n                    else:\n"

wrap_start_idx = content.find(wrap_start_str)
wrap_end_idx = content.find(wrap_end_str) + len(wrap_end_str)

counter_start_idx = content.find(counter_start_str)
counter_end_idx = content.find(counter_end_str)

if wrap_start_idx != -1 and counter_start_idx != -1:
    wrap_block = content[wrap_start_idx:wrap_end_idx]
    counter_block = content[counter_start_idx:counter_end_idx]
    
    pre_wrap = content[:wrap_start_idx]
    post_counter = content[counter_end_idx:]
    
    new_content = pre_wrap + counter_block + wrap_block + post_counter
    
    with open("app/core/daemon.py", "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Swapped successfully.")
else:
    print("Could not find blocks.")
