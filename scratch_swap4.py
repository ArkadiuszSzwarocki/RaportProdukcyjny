import sys

def process():
    with open("app/core/daemon.py", "r", encoding="utf-8") as f:
        content = f.read()

    # Uncommon print logic first
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

    marker_wrap_start = "                        # Initialize wrapped baseline for new plans"
    marker_counter_start = "                        if current_pallet_cnt > 0:"
    marker_counter_end = "                                        _INSTANCE_ID,\n                                    )\n                    else:\n"

    start_A = content.find(marker_wrap_start)
    start_B = content.find(marker_counter_start)
    end_B = content.find(marker_counter_end) + len(marker_counter_end) - 28 # leaves '                    else:\n' out

    if start_A == -1 or start_B == -1 or end_B == -1:
        print(f"Error: {start_A}, {start_B}, {end_B}")
        return

    block_A = content[start_A:start_B]
    block_B = content[start_B:end_B]

    # Swap
    new_content = content[:start_A] + block_B + block_A + content[end_B:]

    with open("app/core/daemon.py", "w", encoding="utf-8") as f:
        f.write(new_content)
    
    print("Success")

process()
