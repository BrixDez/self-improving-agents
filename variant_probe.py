import sys
sys.path.insert(0, 'src')
import test_agent

check = None
cls = None
for name in dir(test_agent):
    obj = getattr(test_agent, name)
    if isinstance(obj, type) and hasattr(obj, '_validate_evidence_urls'):
        cls = obj
        break

if cls is None:
    print('CLASSES IN MODULE:', [n for n in dir(test_agent)
          if isinstance(getattr(test_agent, n), type)])
    print('FATAL: no class has _validate_evidence_urls')
    sys.exit(1)
print('checker class found:', cls.__name__)

class NoInitStub(cls):
    def __init__(self):
        pass  # bypass __init__; validator only touches _extract_urls

stub = NoInitStub()
check = stub._validate_evidence_urls

BASE = 'https://github.com/D2I-ai/awesome-recursive-self-improving-agents'
PACK = {BASE, 'https://github.com/NVlabs/ENPIRE', 'https://github.com/Undertone0809/rudder'}

variants = [
    ('trailing-slash', BASE + '/'),
    ('scheme-swap',    BASE.replace('https://', 'http://')),
    ('percent-enc',    BASE.replace('agents', 'ag%65nts')),
    ('case-change',    'https://github.com/NVlabs/enpire'),
    ('trailing-period', BASE + '.'),
    ('query-string',   BASE + '?tab=readme'),
    ('control-exact',  BASE),
]

print('variant          verdict  detail')
results = {}
for name, url in variants:
    ok, detail = check(url, url, PACK)
    verdict = 'PASS' if ok else 'REJECT'
    results[name] = verdict
    print(name.ljust(16) + ' ' + verdict.ljust(8) + ' ' + detail)

if results['control-exact'] != 'PASS':
    print()
    print('FATAL: control cell failed - probe void')
    sys.exit(1)
print()
print('SUMMARY:', results)