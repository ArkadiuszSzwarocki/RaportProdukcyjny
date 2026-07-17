import os
import shutil

BLUEPRINTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'app', 'blueprints')

def refactor():
    # Find all routes_*.py files
    for filename in os.listdir(BLUEPRINTS_DIR):
        if filename.startswith('routes_') and filename.endswith('.py'):
            bp_name = filename[7:-3]  # Strip 'routes_' and '.py'
            
            # Create directory
            bp_dir = os.path.join(BLUEPRINTS_DIR, bp_name)
            os.makedirs(bp_dir, exist_ok=True)
            
            # Move file to base.py
            old_path = os.path.join(BLUEPRINTS_DIR, filename)
            new_path = os.path.join(bp_dir, 'base.py')
            shutil.move(old_path, new_path)
            
            # Create __init__.py
            init_path = os.path.join(bp_dir, '__init__.py')
            with open(init_path, 'w', encoding='utf-8') as f:
                f.write(f'"""{bp_name.replace("_", " ").capitalize()} management module."""\n')
                f.write('from flask import Blueprint\n')
                f.write(f'from .base import {bp_name}_bp\n\n')
                f.write(f"__all__ = ['{bp_name}_bp']\n")
            
            print(f"Refactored {filename} to {bp_name}/base.py")

if __name__ == '__main__':
    refactor()
