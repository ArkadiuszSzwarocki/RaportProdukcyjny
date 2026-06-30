import sys

def swap_blocks(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    wrap_start_idx = content.find("                        # Initialize wrapped baseline for new plans")
    counter_start_idx = content.find("                        if current_pallet_cnt > 0:")
    else_block_idx = content.find("                    else:", counter_start_idx)

    # find the end of the counter block (the last newline before the else block)
    counter_end_idx = content.rfind("\n", counter_start_idx, else_block_idx) + 1

    pre_wrap = content[:wrap_start_idx]
    wrap_block = content[wrap_start_idx:counter_start_idx]
    counter_block = content[counter_start_idx:counter_end_idx]
    post_counter = content[counter_end_idx:]

    new_content = pre_wrap + counter_block + "\n" + wrap_block + post_counter

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)

swap_blocks("app/core/daemon.py")
