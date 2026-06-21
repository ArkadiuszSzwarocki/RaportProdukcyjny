import os
import importlib.util
import time
import threading
import sys

test_dir = 'tests'
test_files = [f for f in os.listdir(test_dir) if f.startswith('test_') and f.endswith('.py')]

def try_import(filepath, module_name):
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

for file in test_files:
    filepath = os.path.join(test_dir, file)
    module_name = f"tests.{file[:-3]}"
    print(f"Importing {file}...")
    
    # We use a thread to enforce a timeout
    th = threading.Thread(target=try_import, args=(filepath, module_name))
    th.daemon = True
    start = time.time()
    th.start()
    th.join(timeout=15.0)
    
    if th.is_alive():
        print(f"HANG DETECTED: {file}")
        sys.exit(1)
    else:
        print(f"OK: {file} ({time.time() - start:.2f}s)")
