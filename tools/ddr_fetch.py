"""Descarcă Anexa 19 a Documentului de Referință al Rețelei (secții și stații cu restricții de capacitate și manevră)
de pe cfr.ro și o păstrează în DDR_DIR/<an DRR>/Anexa19_<data descărcării>_<sha>.pdf, doar dacă s-a schimbat.
Încearcă DRR-ul anului curent, al anului următor și al celui precedent; pe pagina DRR caută și legătura „Anexa 19”."""
import os, re, sys, hashlib, datetime, urllib.request, urllib.parse, html

DDR = os.environ.get('DDR_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'arhiva', 'ddr'))
UA = {'User-Agent': 'Mozilla/5.0 (restrictii-viteza; GitHub Actions)'}
PAGES = ['https://cfr.ro/?p=77663', 'https://cfr.ro/?p=64232']


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()


def candidates():
    y = datetime.date.today().year
    c = []
    for yy in (y + 1, y, y - 1):
        for n in ('Anexa%2019%20.pdf', 'Anexa%2019.pdf'):
            c.append((yy, f'https://cfr.ro/files/ddr/RO%20{yy}/{n}'))
    for p in PAGES:          # links on the DRR download pages, in case the file name changes
        try:
            t = get(p).decode('utf-8', 'ignore')
        except Exception:
            continue
        for u in re.findall(r'href=["\']([^"\']+\.pdf)["\']', t, re.I):
            u = html.unescape(u); d = urllib.parse.unquote(u)
            m = re.search(r'RO\s*(\d{4})/Anexa\s*19\b', d)
            if m: c.append((int(m[1]), u if u.startswith('http') else 'https://cfr.ro' + u))
    seen = set(); out = []
    for yy, u in c:
        k = urllib.parse.unquote(u).replace(' ', '')
        if k not in seen: seen.add(k); out.append((yy, u))
    return out


def main():
    new = 0; known = set()
    for dp, _, fs in os.walk(DDR):
        for f in fs:
            m = re.search(r'_([0-9a-f]{12})\.pdf$', f)
            if m: known.add(m[1])
    got = set()
    for yy, u in candidates():
        if yy in got: continue
        try:
            b = get(u)
        except Exception as e:
            print('  indisponibil', u, getattr(e, 'code', e)); continue
        if not b.startswith(b'%PDF'): continue
        got.add(yy)
        h = hashlib.sha256(b).hexdigest()[:12]
        if h in known: print('  neschimbată', u); continue
        d = os.path.join(DDR, str(yy)); os.makedirs(d, exist_ok=True)
        f = os.path.join(d, f'Anexa19_{datetime.date.today():%Y-%m-%d}_{h}.pdf')
        open(f, 'wb').write(b); open(f[:-4] + '.url', 'w').write(u); new += 1
        print('  nouă', u, '->', os.path.relpath(f, DDR))
    print('versiuni noi ale Anexei 19:', new)


if __name__ == '__main__':
    main()
