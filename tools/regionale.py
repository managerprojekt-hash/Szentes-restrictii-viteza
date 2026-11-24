"""Regional boundaries from the capacity calculations of the regional branches (CFR, 'REZERVE_Calcul capacitate ...'):
every workbook lists the stations of the sections it calculates, so a station or a section belongs to the branch whose
workbooks list it; frontier stations appear in two branches.  Writes data/regionale.json:
{"st": {station_key: [branches]}, "sec": {"A|B": branch}}.
usage: python3 tools/regionale.py folder_with_xlsx [repo_dir]"""
import os, sys, re, glob, json, collections, unicodedata
import openpyxl

def nkey(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().upper()
    s = re.sub(r'\b(ST|STATIA|HM|HC|HCV|PO|PM|HALTA|HMR|H)\b\.?', ' ', s)
    return re.sub(r'[^A-Z0-9]+', ' ', s).strip()

BUC_UNPREFIXED = ('0802', '0804', '103', '106A', '107', '301M', '301Q', '304C', '304E', '304N', 'Ruse')

def branch(fname):
    b = os.path.basename(fname)
    m = re.search(r'R(\d)_', b)
    if m: return {'1': 'București', '2': 'Craiova', '3': 'Timișoara', '4': 'Cluj', '5': 'Brașov', '6': 'Iași', '7': 'Galați', '8': 'Constanța'}[m.group(1)]
    low = b.lower()
    if 'cluj' in low: return 'Cluj'
    if 'iasi' in low: return 'Iași'
    if 'galati' in low or 'adjud' in low: return 'Galați'
    t = re.sub(r'^REZERVE_(Calcul capacitate - )?', '', b)
    if t.startswith(BUC_UNPREFIXED): return 'București'
    return 'Timișoara'

def stations(ws):
    seq = []; started = False
    for row in ws.iter_rows(values_only=True):
        a = row[0] if row else None
        if isinstance(a, str) and re.match(r'\s*interval', a, re.I): started = True; continue
        if not started or not isinstance(a, str): continue
        t = a.strip()
        if not t or re.match(r'^(total|km|bla|ced|\d)', t, re.I) or len(t) > 60: continue
        seq.append(t)
    return seq

def main():
    src = sys.argv[1]; root = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
    st = collections.defaultdict(set); sec = {}
    for f in sorted(glob.glob(os.path.join(src, '**', '*.xlsx'), recursive=True)):
        br = branch(f)
        try:
            wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
        except Exception as e:
            print('cannot read', f, e); continue
        for ws in wb.worksheets:
            prev = None
            for t in stations(ws):
                parts = [p for p in re.split(r'\s+-\s*|\s*-\s+', t) if p.strip()]
                if len(parts) >= 2:      # 'A - B' interval
                    a, b = nkey(parts[0]), nkey(parts[-1])
                    for k in (a, b):
                        if k: st[k].add(br)
                    if a and b: sec.setdefault(a + '|' + b, br); sec.setdefault(b + '|' + a, br)
                    prev = None; continue
                k = nkey(t)
                if not k: continue
                st[k].add(br)
                if prev and prev != k: sec.setdefault(prev + '|' + k, br); sec.setdefault(k + '|' + prev, br)
                prev = k
    out = dict(st={k: sorted(v) for k, v in st.items()}, sec=sec)
    json.dump(out, open(os.path.join(root, 'data', 'regionale.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
    c = collections.Counter(b for v in out['st'].values() for b in v)
    print(len(out['st']), 'stations,', len(sec) // 2, 'sections;', dict(c), '; frontier stations:', sum(len(v) > 1 for v in out['st'].values()))

if __name__ == '__main__':
    main()
