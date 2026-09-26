import sys, json, sqlite3
from pathlib import Path
sys.path.insert(0, 'src')
from backbone import Backbone
from test_agent import URL_PATTERN

bb = Backbone(Path('data/live.db'))
recs = [r for r in bb.report() if r['job_id'] == 'job-live-002']
print(f'run-2 records: {len(recs)}')

# --- Phase A: locate run-2 evidence pack (trace rows + any data/*.json pack files)
con = sqlite3.connect('data/live.db'); con.row_factory = sqlite3.Row
pack = set(); rows = 0; rejects_logged = []
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
for t in tables:
    for row in con.execute(f'SELECT * FROM "{t}"'):
        d = dict(row); s = json.dumps(d, default=str)
        if 'job-live-002' not in s: continue
        rows += 1
        for v in d.values():
            for u in URL_PATTERN.findall(str(v)):
                pack.add(u.rstrip('.,;:!?'))
        if 'not in evidence pack' in s or 'reject' in s.lower():
            rejects_logged.append(s[:200])
for f in Path('data').glob('**/*.json'):
    s = f.read_text(encoding='utf-8', errors='replace')
    if 'job-live-002' in s or 'github.com' in s:
        for u in URL_PATTERN.findall(s): pack.add(u.rstrip('.,;:!?'))
        print(f'pack file found: {f}')
print(f'trace/pack rows examined: {rows}; candidate pack URLs: {len(pack)}')
print(f'boundary rejections logged for run-2: {len(rejects_logged)}')

# --- Phase B: real check on run-2's 10 records (exact _validate_evidence_urls logic)
def mismatch_type(u, p):
    if u.rstrip('/') in [x.rstrip('/') for x in p]: return 'trailing-slash'
    if u.replace('https://','http://') in p or u.replace('http://','https://') in p: return 'scheme'
    import urllib.parse
    for x in p:
        if urllib.parse.unquote(u) == x or urllib.parse.quote(u, safe='') == x: return 'encoding'
    return 'other/unknown'

counts = {}
for r in recs:
    p = json.loads(r['payload'])
    text = (p.get('source') or '') + ' ' + (p.get('evidence') or '') + ' ' + (p.get('url') or '')
    for u in [x.rstrip('.,;:!?') for x in URL_PATTERN.findall(text)]:
        if u in pack: counts['accepted'] = counts.get('accepted', 0) + 1
        else:
            m = mismatch_type(u, pack); counts[m] = counts.get(m, 0) + 1
            print(f'REJECTED change {r["change_id"]}: {u}  [{m}]')
print('RESULT:', counts or {'accepted': 0})