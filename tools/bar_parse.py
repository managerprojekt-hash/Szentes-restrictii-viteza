"""Reads a CFR speed-restriction bulletin (B.A.R., .docx, one per regional branch and ten-day period) into records.
Table columns (9): no. | track I / single line: km from-to, speed | station or section | switches / diverging tracks:
description, speed | track II: km from-to, speed | remarks.  Each row can hold up to three restrictions (track I,
switches, track II); each becomes one record.  The line comes from the 'LINIA nnn' paragraph before the table.
usage: python3 bar_parse.py file.docx [...]  -> prints a summary; import parse() for records."""
import re, sys, unicodedata
from docx import Document
from docx.oxml.ns import qn

REG = {'BUCURESTI': 'București', 'BRASOV': 'Brașov', 'CLUJ': 'Cluj', 'CONSTANTA': 'Constanța', 'CRAIOVA': 'Craiova',
       'GALATI': 'Galați', 'IASI': 'Iași', 'TIMISOARA': 'Timișoara'}
KM = re.compile(r'(\d{1,3})\s*[+]\s*(\d{1,3})')


def txt(e):
    out = []
    for x in e.iter(qn('w:t'), qn('w:br'), qn('w:p')):
        if x.tag == qn('w:t'): out.append(x.text or '')
        else: out.append('\n')
    return re.sub(r'[ \t ]+', ' ', ''.join(out)).strip()


def norm(s):
    s = unicodedata.normalize('NFC', s or '')
    return s.replace('ş', 'ș').replace('ţ', 'ț').replace('Ş', 'Ș').replace('Ţ', 'Ț')


def kms(s):
    s = re.sub(r'\([^)]*\)', ' ', s or '')          # alternative chainage in brackets, e.g. '0+100 (751+009) 65+795'
    v = [int(a) + int(b) / 1000 for a, b in KM.findall(s)]
    return v


def speed(s):
    s = (s or '').strip()
    if not s: return None, False
    m = re.search(r'\d{1,3}', s)
    if m: return int(m.group(0)), False
    if re.search(r'interz|închis|inchis|oprit', s, re.I): return None, True
    return None, False


def cells(tr):
    out = []
    for tc in tr.findall(qn('w:tc')):
        span = tc.find(qn('w:tcPr'))
        g = 1
        if span is not None and span.find(qn('w:gridSpan')) is not None:
            g = int(span.find(qn('w:gridSpan')).get(qn('w:val')))
        t = txt(tc)
        out += [t] * g
    return out


def meta(doc):
    reg = dec = None
    for p in doc.paragraphs[:40]:
        t = norm(p.text.strip())
        m = re.search(r'B\.?\s*A\.?\s*R\.?\s*([A-ZĂÂÎȘȚ]+)', t.upper())
        if m and not reg: reg = REG.get(re.sub(r'[^A-Z]', '', unicodedata.normalize('NFKD', m.group(1)).encode('ascii', 'ignore').decode()), m.group(1).capitalize())
        m = re.search(r'decada\s+(.+)', t, re.I)
        if m and not dec: dec = m.group(1).strip()
    return reg, dec


def parse(path):
    doc = Document(path); reg, dec = meta(doc)
    recs = []; line = None; ldesc = ''; expect_desc = False
    for e in doc.element.body.iterchildren():
        if e.tag == qn('w:p'):
            t = norm(txt(e))
            m = re.match(r'^LINIA\s+(\d{3,4}\s*[A-Z]?\d?)\b', t.upper().replace('Ș', 'S'))
            if m:
                line = re.sub(r'\s+', '', m.group(1)); expect_desc = True; ldesc = t[len(m.group(0)):].strip(' -–:'); continue
            if expect_desc and t:
                ldesc = (ldesc + ' ' + t).strip(); expect_desc = False
            continue
        if e.tag != qn('w:tbl') or line is None: continue
        expect_desc = False
        for tr in e.findall(qn('w:tr')):
            c = cells(tr)
            if len(c) < 9: c += [''] * (9 - len(c))
            c = [norm(x) for x in c[:9]]
            if 'De la km' in c[1] or 'FIRUL' in c[1].upper() or 'Viteza' in c[2]: continue
            loc = c[3].replace('\n', ' ').strip()
            obs = c[8].replace('\n', ' ').strip()
            for fir, kcol, vcol in (('I', 1, 2), ('II', 6, 7)):
                v, ban = speed(c[vcol])
                if v is None and not ban: continue
                k = kms(c[kcol])
                L = round(abs(k[1] - k[0]), 3) if len(k) >= 2 else None
                ct = 'L' if L is not None and L > 0.05 else 'P'
                recs.append(dict(reg=reg, dec=dec, l=line, ld=ldesc, fir=fir, loc=loc, km0=k[0] if k else None,
                                 km1=k[1] if len(k) > 1 else (k[0] if k else None), L=L, v=v, ban=ban, ct=ct, ap='',
                                 obs=obs, kmtxt=c[kcol].replace('\n', ' ')))
            v, ban = speed(c[5])
            if v is not None or ban:
                k = kms(c[4])
                recs.append(dict(reg=reg, dec=dec, l=line, ld=ldesc, fir='', loc=loc, km0=k[0] if k else None,
                                 km1=k[1] if len(k) > 1 else (k[0] if k else None), L=None, v=v, ban=ban, ct='S',
                                 ap=c[4].replace('\n', ' '), obs=obs, kmtxt=c[4].replace('\n', ' ')))
    return recs


if __name__ == '__main__':
    import collections
    tot = 0
    for f in sys.argv[1:]:
        r = parse(f); tot += len(r)
        c = collections.Counter(x['ct'] for x in r)
        print(f.split('/')[-1], r[0]['reg'] if r else '-', r[0]['dec'] if r else '-', len(r), dict(c),
              'km', round(sum(x['L'] or 0 for x in r if x['ct'] == 'L'), 1), 'lines', len(set(x['l'] for x in r)))
    print('total', tot)
