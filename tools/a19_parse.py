"""Citește Anexa 19 a Documentului de Referință al Rețelei CFR (PDF):
 1) secții cu restricții de capacitate (închideri) -> lista 'inchideri'
 2) stații cu restricții în activitatea de manevră -> lista 'manevra'
usage: python3 a19_parse.py Anexa19.pdf out.json"""
import re, sys, json, collections
import pdfplumber

REGS = ['BUCUREŞTI', 'CRAIOVA', 'TIMIŞOARA', 'CLUJ', 'BRAŞOV', 'IAŞI', 'GALAŢI', 'CONSTANŢA']
REGN = {'BUCUREŞTI': 'București', 'CRAIOVA': 'Craiova', 'TIMIŞOARA': 'Timișoara', 'CLUJ': 'Cluj', 'BRAŞOV': 'Brașov',
        'IAŞI': 'Iași', 'GALAŢI': 'Galați', 'CONSTANŢA': 'Constanța'}
cl = lambda s: re.sub(r'\s+', ' ', (s or '').replace('\n', ' ')).strip()
ro = lambda s: s.replace('ş', 'ș').replace('ţ', 'ț').replace('Ş', 'Ș').replace('Ţ', 'Ț')


def meta(pdf):
    t = pdf.pages[0].extract_text() or ''
    g = lambda r: (re.search(r, t) or [None, None])[1]
    return dict(ddr=g(r'RETELEI CFR\s*-\s*(\d{4})'), valabil=g(r'Valabilitate:\s*([\d.]+\s*[–-]\s*[\d.]+)'),
                versiune=g(r'Versiune:\s*([\d.]+)'), actualizare=g(r'Actualizare:\s*([\d.]+)'))


def iso(d):
    m = re.match(r'(\d{1,2})[./](\d{1,2})[./](\d{4})', d or '')
    return f'{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}' if m else None


DT = re.compile(r'^\d{1,2}[./]\d{1,2}[./]\d{4}$')


def _row(r, k):
    """one closure row, whatever the column layout of that year's annex:
    [nr] linie | de la | până la | [total] | durata | început | sfârșit | categorie | observații (order varies)"""
    di = [i for i, c in enumerate(r) if DT.match(c)]
    if not di: return None
    i0 = di[0]; i1 = di[1] if len(di) > 1 else None
    pre = [(i, c) for i, c in enumerate(r[:i0]) if c]
    tot = any(c.upper() in ('DA', 'TOTAL', 'TOTALĂ') for _, c in pre)
    pre = [(i, c) for i, c in pre if c.upper() not in ('DA', 'NU')]
    z = None
    if pre and re.match(r'^\d+$', pre[-1][1]) and len(pre) >= 4:
        z = int(pre[-1][1]); pre = pre[:-1]
    if len(pre) < 3: return None
    a, b = pre[-2][1], pre[-1][1]; l = pre[-3][1]
    nr = pre[-4][1] if len(pre) >= 4 else str(k)
    post = [c for c in r[(i1 if i1 is not None else i0) + 1:] if c]
    if z is None and post and re.match(r'^\d+$', post[0]): z = int(post.pop(0))
    cat = None
    if post and re.match(r'^[A-D]\b', post[0]): cat = post.pop(0)[:1]
    obs = ' '.join(post)
    otot = bool(re.search(r'INCHIDERE\s+TOTAL|ÎNCHIDERE\s+TOTAL', obs.upper()))
    return dict(_da=tot, _ot=otot, nr=nr, l=l.replace(' ', ''), lx=l, a=ro(a.replace('*', '')), b=ro(b.replace('*', '')), total=tot, zile=z,
                d0=iso(r[i0]), d1=iso(r[i1]) if i1 is not None else None, cat=cat, obs=ro(obs))


def inchideri(pdf):
    out = []
    sec2 = next(i for i, p in enumerate(pdf.pages) if 'activitatea de manevr' in (p.extract_text() or ''))
    for p in pdf.pages[:sec2]:
        for t in p.extract_tables():
            for r in t:
                r = [cl(c) for c in r]
                if not r or not any(DT.match(c) for c in r): continue
                x = _row(r, len(out) + 1)
                if x: out.append(x)
    col = any(x['_da'] for x in out)          # annexes with a 'închidere TOTALĂ' column; older ones say it in the remarks
    for x in out:
        x['total'] = x.pop('_da') if col else x['_ot']
        x.pop('_ot', None)
    return out, sec2


def _bands(p, t):
    """records = runs of shaded cells in the number column (records are separated by thin white strips)"""
    x0 = t.bbox[0]
    R = [r for r in p.rects if r['x0'] <= x0 + 3 and r['x1'] >= x0 + 15 and r['height'] > 2
         and str(r['non_stroking_color']) not in ('1', '1.0', '[1]', '(1,)', '(1, 1, 1)', '[1, 1, 1]')]
    R.sort(key=lambda r: r['top']); B = []
    for r in R:
        c = str(r['non_stroking_color'])
        if B and r['top'] - B[-1][1] < 0.6 and B[-1][2] == c: B[-1][1] = max(B[-1][1], r['bottom'])
        else: B.append([r['top'], r['bottom'], c])
    return B


def _notes(txt):
    out = []; cur = None
    for ln in txt.splitlines():
        s = ln.strip()
        if re.match(r'^(înapoi|Documentul de Refer|Compania Na)', s): cur = None; continue
        if re.match(r'^\*{1,3}\s*[-–]?\s*\S', s) and len(s) > 12:
            cur = s; out.append(cur)
        elif cur and s and not re.match(r'^(Notă|Nota)\s*:?$', s):
            out[-1] += ' ' + s
        elif not s: cur = None
    return [ro(cl(x)) for x in out]


def manevra(pdf, sec2):
    out = []; reg = None; notes = collections.defaultdict(list)
    for p in pdf.pages[sec2 + 1:]:
        txt = p.extract_text() or ''
        m = re.search(r'SUCURSALA\s+REGIONALA\s+CFR\s+([A-ZĂÂÎŞŢȘȚ]+)', txt)
        if m: reg = REGN.get(m[1].replace('Ș', 'Ş').replace('Ț', 'Ţ'), m[1].title())
        if reg:
            for n in _notes(txt):
                if n not in notes[reg]: notes[reg].append(n)
        for t in p.find_tables():
            xs = sorted({round(c[0]) for row in t.rows for c in row.cells if c})
            cols = []
            for x in xs:
                if not cols or x - cols[-1] > 8: cols.append(x)
            if len(cols) < 4: continue
            cols = cols[:4]
            W = [w for w in p.extract_words()
                 if t.bbox[0] - 1 <= w['x0'] <= t.bbox[2] and t.bbox[1] <= w['top'] <= t.bbox[3]]
            col = lambda w: max(i for i, x in enumerate(cols) if w['x0'] >= x - 2) if w['x0'] >= cols[0] - 2 else 0
            nums = [w for w in W if col(w) == 0 and re.match(r'^\d+$', w['text'])]
            if not nums: continue
            yc = lambda w: (w['top'] + w['bottom']) / 2
            B = _bands(p, t)
            def band(y):
                return next((i for i, b in enumerate(B) if b[0] - 0.5 <= y <= b[1] + 0.5), None)
            use_b = B and all(band(yc(n)) is not None for n in nums)
            cy = [yc(n) for n in nums]; nb = [band(c) for c in cy] if use_b else None
            rec = [collections.defaultdict(list) for _ in nums]
            for w in W:
                c = col(w)
                if c == 0: continue
                y = yc(w)
                if use_b:
                    b = band(y)
                    if b is None or b not in nb: continue
                    i = nb.index(b)
                else:
                    if y < cy[0] - 40: continue
                    i = min(range(len(cy)), key=lambda k: abs(cy[k] - y))
                rec[i][c].append((round(w['top']), w['x0'], w['text']))
            for n, r in zip(nums, rec):
                j = lambda c: ro(cl(' '.join(x[2] for x in sorted(r[c]))))
                out.append(dict(nr=n['text'], reg=reg, st=j(1), r=j(2), obs=j(3)))
    return out, dict(notes)


def tip_manevra(r):
    s = (r['r'] + ' ' + r['obs']).lower()
    k = []
    if re.search(r'nu se (descompun|efectueaz|execut)|interzis|fără manevr|fara manevr|nu se fac', s): k.append('interzis')
    if 'descompunere' in s and 'nu se descompun' not in s: k.append('descompunere')
    if re.search(r'ata[șş]are|detașare|detasare|ataşare', s): k.append('atasare')
    if re.search(r'\bsmr\b|\bspt\b', s): k.append('smr')
    if re.search(r'închis|inchis', s): k.append('linii_inchise')
    if re.search(r'fără idm|fara idm|reglementări de lucru', s): k.append('fara_idm')
    if re.search(r'desfiin', s): k.append('desfiintat')
    return k


def tip_inchidere(x):
    s = x['obs'].lower()
    if x['total']: base = 'total'
    elif re.search(r'fir(ul)?\s*(i|ii|1|2)\b|singur fir|un fir\b|firul deschis|pe fir ', s): base = 'fir'
    elif re.search(r'interval(ul)? orar|zilnic|ferestr|\d{1,2}[:.]\d{2}\s*[-–]\s*\d{1,2}[:.]\d{2}', s): base = 'ferestre'
    elif re.search(r'\brv\b|km/h|restric', s): base = 'viteza'
    else: base = 'partial'
    return base


if __name__ == '__main__':
    pdf = pdfplumber.open(sys.argv[1])
    M = meta(pdf)
    I, s2 = inchideri(pdf)
    for x in I: x['tip'] = tip_inchidere(x)
    N, NO = manevra(pdf, s2)
    for r in N: r['k'] = tip_manevra(r)
    json.dump(dict(meta=M, inchideri=I, manevra=N, note=NO), open(sys.argv[2], 'w'), ensure_ascii=False, indent=0)
    print(M, len(I), 'închideri,', len(N), 'stații manevră')
    print(collections.Counter(x['tip'] for x in I))
    print(collections.Counter(r['reg'] for r in N))
    print(collections.Counter(k for r in N for k in r['k']))
