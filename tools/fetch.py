"""Downloads the speed-restriction bulletins (B.A.R.) from the CFR page and files them by ten-day period:
raw/<YYYY-MM-D>/<regionala>.docx.  The period is read from the bulletin itself ('decada 21-30 noiembrie 2026'), not from
the link.  Archives (.zip) are unpacked; old .doc files are converted to .docx with LibreOffice.  Errata files are kept
apart in raw/<period>/erata/.  Already filed periods are skipped unless --all.
usage: python3 tools/fetch.py [--archives] [--all]"""
import os, re, sys, io, zipfile, shutil, subprocess, tempfile, urllib.request, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bar_parse import meta, REG
from build import decade_id
from docx import Document

PAGE = 'https://cfr.ro/ct-menu-item-116-2-2/'
RAW = os.environ.get('RAW_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'raw'))
UA = {'User-Agent': 'Mozilla/5.0 (restrictii-viteza; GitHub Actions)'}


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()


def links():
    t = get(PAGE).decode('utf-8', 'ignore')
    L = [html.unescape(u) for u in re.findall(r'href=["\']([^"\']+\.(?:docx?|zip))["\']', t, re.I)]
    seen = []
    for u in L:
        if u not in seen: seen.append(u)
    return seen


def to_docx(path):
    if path.lower().endswith('.docx'): return path
    out = tempfile.mkdtemp()
    subprocess.run(['soffice', '--headless', '--convert-to', 'docx', '--outdir', out, path], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
    f = [os.path.join(out, x) for x in os.listdir(out) if x.endswith('.docx')]
    return f[0] if f else None


def file_one(path, name_hint=''):
    p = to_docx(path)
    if not p: print('  cannot convert', name_hint); return None
    try:
        reg, dec = meta(Document(p))
    except Exception as e:
        print('  unreadable', name_hint, e); return None
    did = decade_id('decada ' + (dec or '')) if dec else None
    if not did: print('  no period found in', name_hint); return None
    erata = 'erat' in name_hint.lower()
    if not reg and not erata:
        k = re.sub(r'[^a-z]', '', os.path.basename(name_hint).lower().split('-')[0].split('.')[0])
        reg = next((v for kk, v in REG.items() if kk.lower().startswith(k[:4])), None) if k else None
    if not reg and not erata: print('  no regional found in', name_hint); return None
    d = os.path.join(RAW, did, 'erata' if erata else '')
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, (os.path.basename(name_hint) if erata else REG_FILE(reg)))
    if not os.path.exists(dst):
        shutil.copy(p, dst); print('  ', did, reg or 'erata', '->', os.path.relpath(dst, RAW))
    return did


def REG_FILE(reg):
    import unicodedata
    return unicodedata.normalize('NFKD', reg).encode('ascii', 'ignore').decode().lower() + '.docx'


def main():
    archives = '--archives' in sys.argv
    new = set(); force = '--all' in sys.argv
    sp = os.path.join(RAW, 'seen.txt'); os.makedirs(RAW, exist_ok=True)
    seen = set(open(sp).read().split()) if os.path.exists(sp) and not force else set()
    for u in links():
        url = u if u.startswith('http') else 'https://cfr.ro' + u
        if url in seen: continue
        if url.lower().endswith('.zip'):
            if not archives: continue
            print('archive', url)
            try:
                z = zipfile.ZipFile(io.BytesIO(get(url)))
            except Exception as e:
                print('  cannot download', e); continue
            tmp = tempfile.mkdtemp(); z.extractall(tmp)
            for dp, _, fs in os.walk(tmp):
                for f in fs:
                    if f.lower().endswith(('.docx', '.doc')) and not f.startswith('~$'):
                        did = file_one(os.path.join(dp, f), f)
                        if did: new.add(did)
                    elif f.lower().endswith('.zip'):
                        try:
                            zipfile.ZipFile(os.path.join(dp, f)).extractall(os.path.join(dp, f + '_x'))
                        except Exception: pass
            # second pass for nested archives
            for dp, _, fs in os.walk(tmp):
                if '_x' in dp:
                    for f in fs:
                        if f.lower().endswith(('.docx', '.doc')):
                            did = file_one(os.path.join(dp, f), f)
                            if did: new.add(did)
            shutil.rmtree(tmp, ignore_errors=True); seen.add(url)
            continue
        print('bulletin', url)
        tmp = tempfile.mkdtemp(); fp = os.path.join(tmp, os.path.basename(url))
        try:
            open(fp, 'wb').write(get(url))
        except Exception as e:
            print('  cannot download', e); continue
        did = file_one(fp, os.path.basename(url))
        if did: new.add(did); seen.add(url)
        shutil.rmtree(tmp, ignore_errors=True)
    print('periods touched:', ' '.join(sorted(new)))
    open(sp, 'w').write('\n'.join(sorted(seen)) + '\n')
    open(os.environ.get('FETCHED', os.path.join(RAW, '..', '.fetched')), 'w').write('\n'.join(sorted(new)))


if __name__ == '__main__':
    main()
