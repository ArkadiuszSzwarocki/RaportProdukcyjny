import os
import shutil
from datetime import datetime


def clean_logs(log_path='logs/app.log'):
    if not os.path.exists(log_path):
        print('Log file not found:', log_path)
        return

    bak_name = f"{log_path}.{datetime.now().strftime('%Y%m%d%H%M%S')}.bak"
    shutil.copy2(log_path, bak_name)
    print('Backup created:', bak_name)

    kept = []
    removed = 0
    with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            if 'favicon.ico' in line:
                removed += 1
                continue
            kept.append(line)

    with open(log_path, 'w', encoding='utf-8') as f:
        f.writelines(kept)

    print(f'Removed {removed} lines containing "favicon.ico" from {log_path}')


if __name__ == '__main__':
    clean_logs()
