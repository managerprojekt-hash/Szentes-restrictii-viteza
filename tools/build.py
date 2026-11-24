"""Builds the map data from the bulletins kept in raw/<decade>/*.docx:
  data/dec/<decade>.json.gz  restrictions (gzip) of the ten-day period, deduplicated, placed on the map;
  data/index.json         list of the periods with statistics (network, regional branch, trunk line, line).
Decade id: YYYY-MM-D, D = 1 (days 1-10), 2 (11-20), 3 (21-end).
usage: python3 tools/build.py [repo_dir]   (rebuilds only the periods whose json is missing or older than the docx)"""
import os, sys, re, json, glob, gzip, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bar_parse import parse
from locate import Locator, dedupe

ROOT = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
LUNI = ['ianuarie', 'februarie', 'martie', 'aprilie', 'mai', 'iunie', 'iulie', 'august', 'septembrie', 'octombrie', 'noiembrie', 'decembrie']
CLS = [('le15', lambda v: v is not None and v <= 15), ('20_30', lambda v: v is not None and 15 < v <= 30),
       ('35_50', lambda v: v is not None and 30 < v <= 50), ('60_80', lambda v: v is not None and 50 < v <= 80),
       ('gt80', lambda v: v is not None and v > 80), ('int', lambda v: v is None)]


def decade_id(text):
    t = (text or '').lower()
    m = re.search(r'(\d{1,2})\s*[-–]\s*(\d{1,2})\s*([a-zăâîșşțţ]+)\.?\s*(\d{4})', t)
    if m:
        d0, mon, y = int(m.group(1)), m.group(3), int(m.group(4))
        mon = mon.replace('ş', 's').replace('ș', 's')
        mi = next((i + 1 for i, l in enumerate(LUNI) if mon[:3] == l[:3]), None)
        if mi: return f'{y}-{mi:02d}-{1 if d0 <= 5 else 2 if d0 <= 15 else 3}'
    m = re.search(r'(\d{1,2})\s*[-–]\s*(\d{1,2})[-.\s_]+(\d{1,2})[-.\s_]+(\d{4})', t)
    if m:
        d0, mi, y = int(m.group(1)), int(m.group(3)), int(m.group(4))
        if 1 <= mi <= 12: return f'{y}-{mi:02d}-{1 if d0 <= 5 else 2 if d0 <= 15 else 3}'
    return None


def label(did):
    y, m, d = did.split('-'); m = int(m); d = int(d)
    last = {2: 29 if int(y) % 4 == 0 else 28, 4: 30, 6: 30, 9: 30, 11: 30}.get(m, 31)
    a, b = {1: (1, 10), 2: (11, 20), 3: (21, last)}[d]
    return f'{a}–{b} {LUNI[m - 1]} {y}'


def stats(R):
    def agg(rs):
        L = [r for r in rs if r['ct'] == 'L']
        c = collections.Counter(next(k for k, f in CLS if f(r['v'])) for r in rs)
        return dict(n=len(rs), nL=len(L), nP=sum(r['ct'] == 'P' for r in rs), nS=sum(r['ct'] == 'S' for r in rs),
                    km=round(sum(r['L'] or 0 for r in L), 2), pm=round(sum(r['pm'] or 0 for r in rs), 1), cls=dict(c))
    by = lambda f: {k: agg(v) for k, v in sorted(group(R, f).items())}
    return dict(retea=agg(R), regionala=by(lambda r: r['ro'] or '—'), magistrala=by(lambda r: (re.match(r'\d', r['l']).group(0) + '00') if re.match(r'\d', r['l']) else '—'),
                linie=by(lambda r: r['l']))


def group(R, f):
    g = collections.defaultdict(list)
    for r in R: g[f(r)].append(r)
    return g


def build_decade(did, files, loc):
    recs = []; regs = []
    for f in files:
        try:
            r = parse(f)
        except Exception as e:
            print('  cannot read', f, e); continue
        recs += r; regs.append(r[0]['reg'] if r else os.path.basename(f))
    U = dedupe(recs); out = []
    for i, r in enumerate(sorted(U, key=lambda x: (x['l'], x['km0'] if x['km0'] is not None else -1, x['loc']))):
        p = loc.place(r)
        out.append(dict(id=i, l=r['l'], ct=r['ct'], f=r['fir'], loc=r['loc'], km=r['kmtxt'].strip(), k0=r['km0'], k1=r['km1'], L=r['L'],
                        v=r['v'], ban=r['ban'], ap=r['ap'], o=r['obs'], rg=r['rg'], **p))
    return out, sorted(set(regs))


def main():
    base = json.load(open(os.path.join(ROOT, 'data', 'base.json')))
    rp = os.path.join(ROOT, 'data', 'regionale.json')
    if os.path.exists(rp): base['_regionale'] = json.load(open(rp))
    loc = Locator(base)
    os.makedirs(os.path.join(ROOT, 'data', 'dec'), exist_ok=True)
    idx_p = os.path.join(ROOT, 'data', 'index.json')
    idx = json.load(open(idx_p)) if os.path.exists(idx_p) else {'decade': {}}
    RAWS = [os.environ.get('RAW_DIR', os.path.join(ROOT, 'raw'))] + ([os.environ['ARCHIVE_DIR']] if os.environ.get('ARCHIVE_DIR') else [])
    only = set(os.environ.get('PERIODS', '').split()) if os.environ.get('PERIODS') else None
    repo = os.environ.get('GITHUB_REPOSITORY', '')
    for d in sorted(sum((glob.glob(os.path.join(r, '*')) for r in RAWS), [])):
        if not os.path.isdir(d): continue
        did = os.path.basename(d); files = sorted(glob.glob(os.path.join(d, '*.docx')))
        if not files: continue
        jp = os.path.join(ROOT, 'data', 'dec', did + '.json.gz')
        if os.path.exists(jp) and did in idx['decade'] and (only is None or did not in only) and '--all' not in sys.argv: continue
        R, regs = build_decade(did, files, loc)
        with gzip.open(jp, 'wt', encoding='utf-8', compresslevel=9) as fz: json.dump(dict(id=did, label=label(did), regionale=regs, res=R), fz, ensure_ascii=False, separators=(',', ':'))
        idx['decade'][did] = dict(label=label(did), regionale=regs, stats=stats(R),
                                  sursa=open(os.path.join(d, 'sursa.txt')).read().strip() if os.path.exists(os.path.join(d, 'sursa.txt'))
                                  else f'https://github.com/{repo}/tree/arhiva/raw/{did}' if repo else None)
        print(did, label(did), len(R), 'restricții,', len(regs), 'buletine')
    idx['decade'] = dict(sorted(idx['decade'].items()))
    idx['ultima'] = max(idx['decade']) if idx['decade'] else None
    json.dump(idx, open(idx_p, 'w'), ensure_ascii=False, separators=(',', ':'))


if __name__ == '__main__':
    main()
