"""
Split semicolon-separated statements in .py files where it's safe.
Creates a .bak backup for each modified file.

Heuristics (conservative):
- Ignores semicolons inside quotes or inside triple-quoted strings.
- Ignores semicolons inside comments.
- If a colon ':' appears before the first semicolon and the line looks like a block header
  (starts with def/class/if/for/while/try/except/with/else/elif), it moves inline code
  to the next indented line.

Run from repository root: `python tools/split_semicolons.py`
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PY_FILES = list(ROOT.rglob('*.py'))
BLOCK_STARTS = ('def', 'class', 'if', 'elif', 'else', 'for', 'while', 'try', 'except', 'with')


def split_line(line, indent_str='    '):
    # returns list of output lines (without trailing newline)
    # preserve leading indentation
    orig = line.rstrip('\n')
    leading_ws_match = re.match(r"^(\s*)", orig)
    base_indent = leading_ws_match.group(1)
    code = orig[len(base_indent):]

    # find comment start (unescaped # outside quotes)
    in_sq = in_dq = False
    escape = False
    comment_index = None
    for i, ch in enumerate(code):
        if ch == '\\' and not escape:
            escape = True
            continue
        if ch == "'" and not escape and not in_dq:
            in_sq = not in_sq
        elif ch == '"' and not escape and not in_sq:
            in_dq = not in_dq
        elif ch == '#' and not in_sq and not in_dq:
            comment_index = i
            break
        escape = False

    comment = ''
    code_part = code
    if comment_index is not None:
        comment = code[comment_index:]
        code_part = code[:comment_index]

    if ';' not in code_part:
        return [orig]

    # if inside triple-quoted string (not tracked here), we skip; caller should handle multi-line strings

    # find first semicolon position (outside quotes)
    parts = []
    cur = []
    in_sq = in_dq = False
    escape = False
    for ch in code_part:
        if ch == '\\' and not escape:
            escape = True
            cur.append(ch)
            continue
        if ch == "'" and not escape and not in_dq:
            in_sq = not in_sq
        elif ch == '"' and not escape and not in_sq:
            in_dq = not in_dq
        if ch == ';' and not in_sq and not in_dq:
            part = ''.join(cur).strip()
            parts.append(part)
            cur = []
        else:
            cur.append(ch)
        escape = False
    last = ''.join(cur).strip()
    if last:
        parts.append(last)

    # If header-like (colon before first semicolon and starts with block keyword), move header and indent body
    first_semicolon_pos = code_part.find(';')
    colon_pos = code_part.find(':')
    lstripped = code_part.lstrip()
    starts_block = any(lstripped.startswith(k) for k in BLOCK_STARTS)
    result = []
    if colon_pos != -1 and colon_pos < first_semicolon_pos and starts_block:
        # split header at first colon
        prefix_ws = base_indent
        header = code_part[:colon_pos+1].strip()
        rest = code_part[colon_pos+1:]
        # re-split rest by semicolons conservatively
        rest_parts = [p.strip() for p in rest.split(';') if p.strip()]
        result.append(f"{prefix_ws}{header}")
        for p in rest_parts:
            result.append(f"{prefix_ws}{indent_str}{p}")
        if comment:
            # attach comment to last line
            result[-1] = result[-1] + ' ' + comment
    else:
        # normal split: first part stays in place, others get same indentation
        for i, p in enumerate(parts):
            if i == 0:
                result.append(f"{base_indent}{p}")
            else:
                result.append(f"{base_indent}{p}")
        if comment:
            result[-1] = result[-1] + ' ' + comment
    return result


def process_file(path: Path):
    text = path.read_text(encoding='utf-8')
    lines = text.splitlines(keepends=True)
    out_lines = []
    changed = False

    in_triple = False
    triple_delim = None

    for line in lines:
        # detect triple-quoted string start/end
        stripped = line.lstrip()
        if not in_triple:
            # look for triple quote start
            if "'''" in line or '"""' in line:
                # but ensure it's not both start and end on same line with balanced quotes
                # simple heuristic: if count of triple quotes is odd, toggle state
                cnt_single = line.count("'''")
                cnt_double = line.count('"""')
                if (cnt_single + cnt_double) % 2 == 1:
                    # start triple
                    in_triple = True
                    # choose delim (prefer the one present)
                    triple_delim = "'''" if cnt_single else '"""'
            # process only if semicolon appears outside triple strings
            if ';' in line:
                # attempt to split
                parts = split_line(line)
                if len(parts) > 1:
                    changed = True
                    for p in parts:
                        out_lines.append(p + '\n')
                    continue
        else:
            # in triple; check for end
            if triple_delim and triple_delim in line:
                in_triple = False
                triple_delim = None
        out_lines.append(line)

    if changed:
        bak = path.with_suffix(path.suffix + '.bak')
        path.rename(bak)
        path.write_text(''.join(out_lines), encoding='utf-8')
        print(f"Modified: {path} (backup at {bak.name})")
    return changed


if __name__ == '__main__':
    modified_files = []
    for f in PY_FILES:
        # skip virtualenv, .git, migrations, etc.
        if any(p in f.parts for p in ('.venv', 'venv', 'env', '.git')):
            continue
        try:
            if process_file(f):
                modified_files.append(str(f.relative_to(ROOT)))
        except Exception as e:
            print(f"Error processing {f}: {e}")

    print('\nSummary:')
    print(f"Files modified: {len(modified_files)}")
    for m in modified_files:
        print(' -', m)
