"""Stațiile și haltele de cale ferată din România, din OpenStreetMap (Overpass API) -> data/statii_osm.json
[[nume, lat, lng, tip, alte_nume], ...].  Folosit pentru stațiile din Anexa 19 care nu apar în rețeaua TUI."""
import json, os, sys, time, urllib.request, urllib.parse

Q = """[out:json][timeout:180][bbox:43.55,20.20,48.30,29.80];
(node["railway"~"^(station|halt|yard|service_station|junction|crossing_station)$"];
 node["public_transport"="station"]["train"="yes"];);
out;"""
SRV = ['https://overpass-api.de/api/interpreter', 'https://overpass.private.coffee/api/interpreter',
       'https://maps.mail.ru/osm/tools/overpass/api/interpreter', 'https://overpass.kumi.systems/api/interpreter']
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'statii_osm.json')
for s in SRV:
    try:
        req = urllib.request.Request(s, data=urllib.parse.urlencode({'data': Q}).encode(),
                                     headers={'User-Agent': 'Szentes-restrictii-viteza (GitHub Actions)'})
        d = json.load(urllib.request.urlopen(req, timeout=240)); print('ok', s, len(d.get('elements', []))); break
    except Exception as e:
        print('eșec', s, repr(e)[:300]); time.sleep(5); d = None
if not d: sys.exit(1)
R = []
for e in d['elements']:
    t = e.get('tags', {}); n = t.get('name') or t.get('name:ro')
    if not n: continue
    lat = e.get('lat') or e.get('center', {}).get('lat'); lon = e.get('lon') or e.get('center', {}).get('lon')
    alt = [t[k] for k in ('name:ro', 'alt_name', 'old_name', 'official_name', 'short_name') if t.get(k) and t[k] != n]
    R.append([n, round(lat, 5), round(lon, 5), t.get('railway', ''), alt])
R.sort()
json.dump(R, open(out, 'w'), ensure_ascii=False, separators=(',', ':'))
print(len(R), 'stații')
