import re
import glob
import os

LOG_PATH = os.path.join(os.path.dirname(__file__), '..', 'logs', 'app.log')
SNAP_GLOB = os.path.join(os.path.dirname(__file__), 'last_zasyp_response_*.html')

def parse_after_commit(log_text):
    vals = []
    for m in re.finditer(r"After commit: plan_id=316 tonaz_rzeczywisty=([0-9]+(?:\.[0-9]+)?)", log_text):
        vals.append(int(float(m.group(1))))
    return vals


def extract_header_wykonanie(html):
    m = re.search(r'class="stat-inline stat-wykonanie"[\s\S]*?<strong[^>]*>([^<]+) kg', html)
    if not m:
        return None
    s = m.group(1)
    s = s.replace('\xa0', ' ')
    s = re.sub(r'[^0-9]', '', s)
    return int(s) if s else None


def extract_plan_row_realizacja(html, plan_id='315'):
    # Locate the button occurrence and then find its parent <tr> by index search (more robust)
    token = "toggleDetails('{}')".format(plan_id)
    idx = html.find(token)
    if idx == -1:
        return None
    # find the last <tr before idx
    tr_start = html.rfind('<tr', 0, idx)
    tr_end = html.find('</tr>', idx)
    if tr_start == -1 or tr_end == -1:
        return None
    tr_html = html[tr_start:tr_end+5]
    # find all <td> inside tr_html
    tds = re.findall(r'<td[^>]*>([\s\S]*?)</td>', tr_html)
    # Realizacja is 6th td (index 5)
    if len(tds) >= 6:
        td = tds[5]
        m = re.search(r'>?\s*<strong[^>]*>([0-9\s,]+) kg', td)
        if not m:
            # maybe without <strong>
            m = re.search(r'([0-9\s,]+) kg', td)
        if m:
            s = m.group(1)
            s = re.sub(r'[^0-9]', '', s)
            return int(s) if s else 0
    return None


def main():
    # read log
    try:
        with open(LOG_PATH, 'r', encoding='utf-8') as f:
            log_text = f.read()
    except FileNotFoundError:
        print('Log file not found:', LOG_PATH)
        return

    after_vals = parse_after_commit(log_text)
    if not after_vals:
        print('No After commit entries for plan_id=316 found in log')
    else:
        print('Found', len(after_vals), 'After commit entries (plan_id=316). Latest:', after_vals[-1])

    files = sorted(glob.glob(SNAP_GLOB))
    if not files:
        print('No snapshot files found matching', SNAP_GLOB)
        return

    report = []
    for f in files:
        with open(f, 'r', encoding='utf-8') as fh:
            html = fh.read()
        header = extract_header_wykonanie(html)
        plan_real = extract_plan_row_realizacja(html, '315')
        # determine match: plan_real equals any after_vals or plan_real==0 while after_vals nonzero
        matches_any = (plan_real in after_vals) if plan_real is not None else False
        latest_after = after_vals[-1] if after_vals else None
        status = 'OK' if matches_any else 'MISMATCH'
        # also mark if plan_real==0 but latest_after>0
        if plan_real == 0 and latest_after and latest_after > 0:
            status = 'MISMATCH (0 vs after {})'.format(latest_after)
        report.append((os.path.basename(f), header, plan_real, status))

    # print report
    print('\nPer-snapshot summary:')
    ok = 0
    bad = 0
    for row in report:
        fn, head, planv, status = row
        print(f"{fn}: header_wykonanie={head} kg, plan_315_realizacja={planv} kg, status={status}")
        if status.startswith('OK'):
            ok += 1
        else:
            bad += 1
    print('\nTotals: OK={}, MISMATCH={}'.format(ok, bad))

if __name__ == '__main__':
    main()
