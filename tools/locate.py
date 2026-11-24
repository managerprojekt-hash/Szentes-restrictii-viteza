"""Places restrictions on the map and attaches the network attributes, using the reference network (base.json):
- stations: coordinates from the TUI section end points (section name 'A - B': first point = A, last point = B);
- km on a line: piecewise-linear interpolation between calibration points (km -> lat/lng) of that line;
- owning regional branch, TUI section and maximum speed: from the nearest calibration point of the line;
- time lost by a passenger train: L * (1/v - 1/vmax) * 60 (no braking / acceleration).
Deduplicates the restrictions that appear in several regional bulletins."""
import re, json, bisect, unicodedata, collections

def dist(a, b):
    import math
    return math.hypot((a[0] - b[0]) * 111.2, (a[1] - b[1]) * 111.2 * math.cos(math.radians((a[0] + b[0]) / 2)))


def nkey(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().upper()
    s = re.sub(r'\b(ST|STATIA|HM|HC|HCV|PO|PM|HALTA|HMR)\b\.?', ' ', s)
    return re.sub(r'[^A-Z0-9]+', ' ', s).strip()


SEAT = {'București': (44.447, 26.074), 'Craiova': (44.330, 23.794), 'Timișoara': (45.750, 21.208), 'Cluj': (46.784, 23.586),
        'Brașov': (45.661, 25.613), 'Iași': (47.165, 27.570), 'Galați': (45.437, 28.035), 'Constanța': (44.174, 28.613)}


class Locator:
    def __init__(self, base):
        self.B = base
        self.st = {}
        for n in base['net']:
            parts = [p.strip() for p in re.split(r'\s+-\s+', n['n'])]
            if len(parts) >= 2:
                self.st.setdefault(nkey(parts[0]), n['p'][0]); self.st.setdefault(nkey(parts[-1]), n['p'][-1])
        for loc, g in base.get('stl', []):
            w = self.words(loc)
            for k in range(min(4, len(w)), 0, -1):
                self.st.setdefault(' '.join(w[:k]), g)
        self.cal = collections.defaultdict(list)        # line -> [(km, lat, lng, ro, s, vx)]
        for c in base['cal']: self.cal[c[0]].append(tuple(c[1:]))
        for l in self.cal: self.cal[l].sort(key=lambda x: x[0])
        self.ro_line = {}
        for l, v in self.cal.items():
            self.ro_line[l] = collections.Counter(x[3] for x in v).most_common(1)[0][0]

    def line_cal(self, l):
        if l in self.cal: return self.cal[l]
        m = re.match(r'\d+', l)
        if m and m.group(0) in self.cal: return self.cal[m.group(0)]
        return []

    def at_km(self, l, km):
        c = self.line_cal(l)
        if not c or km is None: return None
        ks = [x[0] for x in c]; i = bisect.bisect_left(ks, km)
        if i <= 0: a = b = c[0]
        elif i >= len(c): a = b = c[-1]
        else: a, b = c[i - 1], c[i]
        if abs(km - a[0]) > 25 and abs(km - b[0]) > 25: return None     # too far from any calibration point
        t = 0 if b[0] == a[0] else (km - a[0]) / (b[0] - a[0])
        near = a if abs(km - a[0]) <= abs(km - b[0]) else b
        return [round(a[1] + t * (b[1] - a[1]), 5), round(a[2] + t * (b[2] - a[2]), 5)], near

    @staticmethod
    def words(loc):
        t = re.sub(r'^\s*(St|Stația|Hm|H|Hc|Po|Pm|Hcv)\.?\s+', '', loc or '', flags=re.I)
        t = re.split(r',|\b(linia|liniile|cap|capul|grupa|peste|între|intre|axa|sch|diag|tdj)\b', t, flags=re.I)[0]
        return nkey(t).split()

    def station(self, loc):
        w = self.words(loc)
        for k in range(min(5, len(w)), 0, -1):
            key = ' '.join(w[:k])
            if key in self.st: return self.st[key]
            if k >= 2 or len(key) >= 5:
                for kk, g in self.st.items():
                    if kk.startswith(key + ' ') and k >= 2: return g
        return None

    def place(self, r):
        g = None; near = None
        if r['ct'] in ('L', 'P') and r['km0'] is not None:
            a = self.at_km(r['l'], r['km0']); b = self.at_km(r['l'], r['km1'])
            if a and b:
                g = [a[0]] if r['ct'] == 'P' or a[0] == b[0] else [a[0], b[0]]; near = a[1]
                if len(g) == 2 and dist(g[0], g[1]) > 1.5 * (r['L'] or 0) + 3:
                    g = None          # calibration not consistent here: place by the station names instead
        if g is None:
            p = self.station(r['loc'])
            if p is None:
                parts = re.split(r'\s+-\s+', r['loc'])
                if len(parts) >= 2:
                    pa, pb = self.station(parts[0]), self.station(parts[1])
                    if pa and pb: p = [round((pa[0] + pb[0]) / 2, 5), round((pa[1] + pb[1]) / 2, 5)]
            if p is not None: g = [p]
        if near is None and r['km0'] is not None:
            a = self.at_km(r['l'], r['km0']); near = a[1] if a else None
        ro = near[3] if near else self.ro_line.get(r['l']) or self.ro_line.get(re.match(r'\d*', r['l']).group(0), r['reg'])
        if g:   # owning branch: the nearest regional seat among the branches whose bulletins list the restriction
            cand = [x for x in r.get('rg', []) if x in SEAT] or list(SEAT)
            ro = min(cand, key=lambda x: dist(g[0], SEAT[x]))
        s = near[4] if near else ''
        vx = near[5] if near else None
        pm = None
        if r['ct'] == 'L' and r['L'] and r['v'] and vx and vx > r['v']:
            pm = round(r['L'] * (1 / r['v'] - 1 / vx) * 60, 2)
        return dict(g=g, ro=ro, s=s, vx=vx, pm=pm)


def dedupe(recs):
    out = {}
    for x in recs:
        k = (x['l'], x['ct'], x['fir'], x['km0'], x['km1'], x['v'], x['ban'],
             nkey(x['loc']) if x['ct'] == 'S' or x['km0'] is None else '', nkey(x['ap']))
        if k in out: out[k]['rg'].add(x['reg'])
        else:
            y = dict(x); y['rg'] = {x['reg']}; out[k] = y
    for y in out.values(): y['rg'] = sorted(y['rg'])
    return list(out.values())
