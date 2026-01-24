import os
import py_compile


def is_ignored(path):
    parts = path.split(os.sep)
    if '.venv' in parts or '__pycache__' in parts or 'backups' in parts:
        return True
    return False


def main(root='.'):
    errors = []
    for dirpath, dirnames, filenames in os.walk(root):
        # skip hidden and virtualenv dirs
        if is_ignored(dirpath):
            continue
        for fn in filenames:
            if not fn.endswith('.py'):
                continue
            fp = os.path.join(dirpath, fn)
            try:
                py_compile.compile(fp, doraise=True)
            except py_compile.PyCompileError as e:
                errors.append((fp, str(e)))

    if errors:
        print('Syntax errors found:')
        for fp, msg in errors:
            print(f'- {fp}: {msg}')
        raise SystemExit(1)
    else:
        print('No Python syntax errors found.')


if __name__ == '__main__':
    main('.')
