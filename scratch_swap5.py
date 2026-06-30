import sys

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

    marker_wrap_start = "                        # Initialize wrapped baseline for new plans, then only print on False->True transitions.\n"
    marker_wrap_end = "                            plan_wrap_states[plan_id] = current_wrapped\n"

    start_A = content.find(marker_wrap_start)
    end_A = content.find(marker_wrap_end, start_A) + len(marker_wrap_end)

    marker_counter_start = "                        if current_pallet_cnt > 0:\n"
    marker_counter_end = "                                        _INSTANCE_ID,\n                                    )\n"

    start_B = content.find(marker_counter_start)
    end_B = content.find(marker_counter_end, start_B) + len(marker_counter_end)

    if start_A == -1 or start_B == -1 or end_A == -1 or end_B == -1:
        print(f"Error finding blocks: {start_A}, {end_A}, {start_B}, {end_B}")
        return

    block_A = content[start_A:end_A]
    block_B = content[start_B:end_B]

    print(f"Block A len: {len(block_A)}, Block B len: {len(block_B)}")
    print(f"Block A ends with: {repr(block_A[-20:])}")
    print(f"Block B ends with: {repr(block_B[-20:])}")

    # Now swap:
    new_content = content[:start_A] + block_B + "\n" + block_A + content[end_B:]

    with open("app/core/daemon.py", "w", encoding="utf-8") as f:
        f.write(new_content)
    
    print("Success")

process()
