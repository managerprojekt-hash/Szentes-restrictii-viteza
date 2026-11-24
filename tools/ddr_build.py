"""Hărțile din Anexa 19 a DRR (restricții de capacitate și de manevră).
Intrare: PDF-urile anexei (DDR_DIR/<an>/*.pdf); ieșire: data/ddr/<id>.json și data/ddr/index.json.
 - închideri de secție: traseul urmează rețeaua TUI între cele două stații (drum cel mai scurt, cu preferință pentru
   linia indicată în anexă), lungimea este suma secțiilor TUI parcurse;
 - restricții de manevră: punct în stație, categoria după operațiile restricționate.
usage: python3 tools/ddr_build.py [--all]"""
import os, re, sys, json, glob, heapq, hashlib, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from locate import Locator, nkey, dist, SEAT
import a19_parse, pdfplumber

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
DDR = os.environ.get('DDR_DIR', os.path.join(ROOT, 'arhiva', 'ddr'))


ABR = [(r'^Buc\.?\s*N(ord)?\.?\s*(?=Post|$)', 'București Nord '), (r'^Buc\.\s*N(ord)?\.?\s*', 'București Nord '),
       (r'^Buc\.\s*', 'București '), (r'^Tg\.\s*', 'Târgu '), (r'^C-lung\b', 'Câmpulung'), (r'^V\.\s*', 'Valea '),
       (r'^PL\.\s*', 'Plaiu '), (r'^G-ral\.\s*', 'General '), (r'^Dr\.\s*Tr\.\s*', 'Drobeta Turnu '),
       (r'^Rm\.\s*', 'Râmnicu '), (r'^Sf\.\s*', 'Sfântu '), (r'^Ram(ificatia|ificația|ificație|\.)?\s+', ''),
       (r'^Cluj-\s*Napoca', 'Cluj Napoca'), (r'\s+Tj$', ' Triaj'), (r'\s+Mf$', ' Mărfuri')]


def clean_name(s):
    s = re.sub(r'^(de mișcare|de miscare)\s+', '', s or '', flags=re.I).strip()
    s = re.sub(r'^(H\.\s*m\.|Hm\.|HM|Hm|H\.m\.|St\.|Stația|Halta)\s+', '', s)
    s = re.sub(r'\s*\*+\s*$', '', s)
    s = re.sub(r'\s+(HM|Hm|hm|hcv|Hcv|HCV|Hc|PO|Po)\b\.?\s*\**$', '', s)
    s = re.sub(r'\s*-\s*linia\s*\d+\s*$', '', s, flags=re.I)
    s = re.sub(r'\s*\*+\s*$', '', s)
    for a, b in ABR: s = re.sub(a, b, s)
    return re.sub(r'\s+', ' ', s).strip()


def variants(name):
    v = [name]
    if 'î' in name[1:-1] or 'Î' in name: v.append(re.sub(r'(?<=\w)î(?=\w)', 'â', name))
    if 'â' in name: v.append(name.replace('â', 'î'))
    return v


class Gaz:
    """stațiile din OpenStreetMap (data/statii_osm.json), căutare după nume normalizat"""
    def __init__(self, path):
        self.N = collections.defaultdict(list)
        if os.path.exists(path):
            for n, la, lo, t, alt in json.load(open(path)):
                for x in [n] + alt:
                    self.N[nkey(x)].append((la, lo, t))
                    k2 = re.sub(r'\b(HALTA|STATIA|GARA|HM|HC|HCV|PO|CF|CFR)\b', ' ', nkey(x)); k2 = re.sub(r'\s+', ' ', k2).strip()
                    if k2 != nkey(x): self.N[k2].append((la, lo, t))

    def get(self, name, near=None):
        for v in variants(name):
            k = nkey(v)
            for kk in (k, k.replace(' NORD', ' N'), re.sub(r'\s+(SAT|ORAS)$', '', k)):
                c = self.N.get(kk)
                if c:
                    c = sorted(c, key=lambda x: (x[2] not in ('station', 'halt'), dist(near, x[:2]) if near else 0))
                    return [c[0][0], c[0][1]]
        return None


class Net:
    def __init__(self, base, loc):
        self.loc = loc; self.E = collections.defaultdict(list); self.P = {}
        for i, n in enumerate(base['net']):
            parts = [p.strip() for p in re.split(r'\s+-\s+', n['n'])]
            if len(parts) < 2 or not n['p']: continue
            a, b = nkey(parts[0]), nkey(parts[-1])
            self.P.setdefault(a, n['p'][0]); self.P.setdefault(b, n['p'][-1])
            self.E[a].append((b, i, n['L'] or dist(n['p'][0], n['p'][-1]), n['l']))
            self.E[b].append((a, i, n['L'] or dist(n['p'][0], n['p'][-1]), n['l']))
        self.B = base

    def coord(self, name, near=None):
        """coordonatele stației: rețeaua TUI (nume exact), OpenStreetMap, apoi locurile restricțiilor de viteză"""
        for v in variants(name):
            k = nkey(v)
            if k in self.P: return self.P[k], k
        g = self.gaz.get(name, near) if self.gaz else None
        if g: return g, None
        for v in variants(name):
            w = [x for x in Locator.words(v) if x not in ('H', 'M', 'HM')]
            for k in range(min(5, len(w)), 1, -1):
                key = ' '.join(w[:k])
                hits = [kk for kk in self.P if kk.startswith(key + ' ')]
                if hits: kk = min(hits, key=len); return self.P[kk], kk
            g = self.loc.station(v)
            if g: return g, None
            if len(w) == 1 and w[0] in self.P: return self.P[w[0]], w[0]
        return None, None

    def node_at(self, g, maxd=3.0):
        best = min(self.P, key=lambda k: dist(self.P[k], g))
        return best if dist(self.P[best], g) <= maxd else None

    def path(self, a, b, line):
        lp = re.match(r'\d+', line or ''); lp = lp.group(0) if lp else None
        D = {a: 0}; prev = {}; h = [(0, a)]
        while h:
            d, u = heapq.heappop(h)
            if u == b: break
            if d > D.get(u, 1e18) or d > 400: continue
            for v, i, L, l in self.E[u]:
                ll = re.match(r'\d+', l or ''); ll = ll.group(0) if ll else None
                w = L * (1 if lp and ll == lp else 2.2)
                if d + w < D.get(v, 1e18):
                    D[v] = d + w; prev[v] = (u, i); heapq.heappush(h, (d + w, v))
        if b not in prev and a != b: return None
        seq = []; u = b
        while u != a: u, i = prev[u]; seq.append(i)
        return seq[::-1]


def place_inchideri(I, net, loc):
    ok = 0
    for x in I:
        x['a'] = clean_name(x['a']); x['b'] = clean_name(x['b'])
        x['g'] = None; x['km'] = None; x['s'] = []
        ga, a = net.coord(x['a']) if x['a'] else (None, None)
        gb, b = net.coord(x['b'], ga) if x['b'] else (None, None)
        if ga and not a and gb: ga, a = net.coord(x['a'], gb)
        if ga and gb and dist(ga, gb) > 120: gb = None          # nume identic în altă parte a țării
        a = a or (net.node_at(ga) if ga else None); b = b or (net.node_at(gb) if gb else None)
        if a and b and a != b:
            seq = net.path(a, b, x['l']); straight = dist(net.P[a], net.P[b])
            if seq:
                km = sum(net.B['net'][i]['L'] or 0 for i in seq)
                lp = re.match(r'\d+', x['l'] or ''); lp = lp.group(0) if lp else '-'
                on = sum(L for i in seq for L in [net.B['net'][i]['L'] or 0] if re.match(r'\d+', net.B['net'][i]['l'] or '') and re.match(r'\d+', net.B['net'][i]['l']).group(0) == lp)
                if km <= 1.6 * straight + 8 or (on >= 0.9 * km and km <= 3 * straight + 15):
                    x['g'] = seq; x['km'] = round(km, 2); ok += 1
                    x['s'] = sorted({(net.B['net'][i]['t'] or '').lower() for i in seq} - {''})
        if x['g'] is None:
            if ga and gb and ga != gb: x['g'] = [[ga, gb]]; x['km'] = round(dist(ga, gb), 1); x['aprox'] = True
            elif ga or gb: x['g'] = [[ga or gb]]; x['aprox'] = True
        g0 = None
        if x['g']:
            g0 = net.B['net'][x['g'][0]]['p'][0] if isinstance(x['g'][0], int) else x['g'][0][0]
        x['ro'] = loc.branch({'loc': f"{x['a']} - {x['b']}", 'rg': []}, [g0] if g0 else None)
        if not x['ro'] and g0: x['ro'] = min(SEAT, key=lambda r: dist(g0, SEAT[r]))
    return ok


CAT = [('desc', r'descomp|descompunre'), ('comp', r'(?<!des)compun'), ('atas', r'ata[sș]|deta[sș]|cupluri'),
       ('smr', r'\bsmr\b|\bspt\b|schimb\w* mijloc'), ('inch', r'închis|inchis'), ('fara', r'fără restric|fara restric')]


def cats(r):
    s = r['r'].lower(); k = [c for c, rx in CAT if re.search(rx, s)]
    if not k: k = ['alte']
    return k


def place_manevra(N, net):
    ok = 0
    for r in N:
        r['st'] = re.sub(r'\s*\*+\s*$', '', re.sub(r'^(de mișcare|de miscare)\s+', '', r['st'], flags=re.I)).strip()
        r['k'] = cats(r)
        g, _ = net.coord(clean_name(r['st']), SEAT.get(r['reg']))
        if g and r['reg'] in SEAT and dist(g, SEAT[r['reg']]) > 330: g = None
        r['g'] = g; ok += g is not None
    return ok


def build_one(pdf_path, net, loc):
    pdf = pdfplumber.open(pdf_path)
    M = a19_parse.meta(pdf)
    I, s2 = a19_parse.inchideri(pdf)
    for x in I: x['tip'] = a19_parse.tip_inchidere(x)
    N, NO = a19_parse.manevra(pdf, s2)
    oi = place_inchideri(I, net, loc); om = place_manevra(N, net)
    print(os.path.basename(pdf_path), M, f'{len(I)} închideri ({oi} pe traseu)', f'{len(N)} stații manevră ({om} localizate)')
    return M, I, N, NO


def main():
    base = json.load(open(os.path.join(ROOT, 'data', 'base.json')))
    rp = os.path.join(ROOT, 'data', 'regionale.json')
    if os.path.exists(rp): base['_regionale'] = json.load(open(rp))
    loc = Locator(base); net = Net(base, loc); net.gaz = Gaz(os.path.join(ROOT, 'data', 'statii_osm.json'))
    od = os.path.join(ROOT, 'data', 'ddr'); os.makedirs(od, exist_ok=True)
    ip = os.path.join(od, 'index.json')
    idx = json.load(open(ip)) if os.path.exists(ip) and '--all' not in sys.argv else {'versiuni': {}}
    for f in sorted(glob.glob(os.path.join(DDR, '*', '*.pdf'))):
        h = hashlib.sha256(open(f, 'rb').read()).hexdigest()[:12]
        if any(v.get('sha') == h for v in idx['versiuni'].values()): continue
        try:
            M, I, N, NO = build_one(f, net, loc)
        except Exception as e:
            print('nu pot citi', f, e); continue
        if not I and not N: continue
        a = M.get('actualizare') or ''
        vid = f"{M.get('ddr') or os.path.basename(os.path.dirname(f))}-" + ('-'.join(a.split('.')[::-1]) if a else h)
        json.dump(dict(id=vid, meta=M, inchideri=I, manevra=N, note=NO), open(os.path.join(od, vid + '.json'), 'w'),
                  ensure_ascii=False, separators=(',', ':'))
        rel = os.path.relpath(f, DDR).replace(os.sep, '/')
        up = f[:-4] + '.url'
        url = open(up).read().strip() if os.path.exists(up) else None
        idx['versiuni'][vid] = dict(meta=M, sha=h, pdf=rel, url=url, ni=len(I), nm=len(N))
    idx['versiuni'] = dict(sorted(idx['versiuni'].items()))
    idx['ultima'] = max(idx['versiuni']) if idx['versiuni'] else None
    json.dump(idx, open(ip, 'w'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
