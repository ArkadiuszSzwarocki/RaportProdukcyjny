import os
import shutil
import subprocess

def get_stash_files():
    try:
        result = subprocess.run(['git', 'stash', 'show', '--include-untracked', 'stash@{0}', '--name-only'], 
                             capture_output=True, text=True, check=True)
        return result.stdout.splitlines()
    except Exception as e:
        print(f"Error getting stash files: {e}")
        return []

def backup_conflicting_files(files):
    backup_dir = 'backup_before_stash_restore'
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    
    conflicts = []
    for f in files:
        if os.path.exists(f) and not os.path.isdir(f):
            dest = os.path.join(backup_dir, f)
            dest_dir = os.path.dirname(dest)
            if not os.path.exists(dest_dir):
                os.makedirs(dest_dir)
            print(f"Moving {f} to {dest}")
            shutil.move(f, dest)
            conflicts.append(f)
    return conflicts

if __name__ == "__main__":
    files = get_stash_files()
    if files:
        moved = backup_conflicting_files(files)
        print(f"Moved {len(moved)} conflicting files to backup_before_stash_restore")
    else:
        print("No files found in stash or error occurred.")
