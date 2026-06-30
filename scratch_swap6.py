import sys
import re

def process():
    with open("app/core/daemon.py", "r", encoding="utf-8") as f:
        content = f.read()

    # Uncomment
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

    # Find Block A: from "Initialize wrapped baseline" until just before "if current_pallet_cnt > 0:"
    pattern_A = r"(                        # Initialize wrapped baseline for new plans.*?)                        if current_pallet_cnt > 0:\n"
    match_A = re.search(pattern_A, content, re.DOTALL)
    
    if not match_A:
        print("Block A not found")
        return
        
    block_A = match_A.group(1)

    # Find Block B: from "if current_pallet_cnt > 0:" until just before "else:"
    pattern_B = r"(                        if current_pallet_cnt > 0:\n.*?)                    else:\n"
    match_B = re.search(pattern_B, content, re.DOTALL)
    
    if not match_B:
        print("Block B not found")
        return
        
    block_B = match_B.group(1)

    print(f"Block A length: {len(block_A)}")
    print(f"Block B length: {len(block_B)}")

    # Make the swap
    # We replace the concatenated original blocks with swapped blocks.
    original_combined = block_A + block_B
    swapped_combined = block_B + block_A

    new_content = content.replace(original_combined, swapped_combined)

    with open("app/core/daemon.py", "w", encoding="utf-8") as f:
        f.write(new_content)
    
    print("Success")

process()
