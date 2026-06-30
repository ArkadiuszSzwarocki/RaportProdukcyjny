from app.core.daemon import _print_wrapped_pallet_label_once
last={}
ok, msg, pid = _print_wrapped_pallet_label_once(209, last)
print(f"Result for 209: {ok}, {msg}, {pid}")
ok, msg, pid = _print_wrapped_pallet_label_once(208, last)
print(f"Result for 208: {ok}, {msg}, {pid}")
