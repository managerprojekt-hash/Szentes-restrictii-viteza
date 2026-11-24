# Restricții de viteză pe rețeaua CFR

Hartă interactivă a restricțiilor de viteză din buletinele de avizare (B.A.R.) ale celor 8 regionale CNCF „CFR” SA, cu arhivă pe decade și comparații în timp.

**Harta:** https://managerprojekt-hash.github.io/Szentes-restrictii-viteza/

## Ce face

- alegeți orice decadă din arhivă și o comparați cu decada anterioară, cu aceeași decadă de acum un an sau cu oricare alta: restricțiile apărute, ridicate, înăsprite și relaxate;
- statistici pe rețea, regionale, magistrale și linii: număr de restricții, km de fir restricționați, timp pierdut estimat;
- evoluția în timp și aceeași decadă în fiecare an (2020–2026);
- descărcarea selecției în CSV, pentru verificare.

## Cum se actualizează

Fluxul `.github/workflows/actualizare.yml` rulează la începutul fiecărei decade (zilele 1, 11 și 21, la 00:10, cu o a doua încercare la 08:10): citește pagina CFR (https://cfr.ro/ct-menu-item-116-2-2/), descarcă buletinele noi, le păstrează în ramura `arhiva` (buletinele originale, `raw/<decada>/<regionala>.docx`), le citește și actualizează datele hărții (`data/`).

Pornire manuală: **Actions → Actualizare restricții de viteză → Run workflow**; bifați „arhivele ZIP” pentru a încărca și buletinele din 2020–2025.

## Structura

- `index.html`: aplicația (Leaflet, fără servicii externe);
- `data/regionale.json`: frontierele regionalelor (stațiile și secțiile din calculele de capacitate ale fiecărei regionale), pentru atribuirea restricțiilor;
- `data/base.json`: rețeaua (secțiile TUI, vitezele maxime, capacitățile) și punctele de calibrare km → hartă;
- `data/index.json`: lista decadelor și statisticile;
- `data/dec/<decada>.json`: restricțiile fiecărei decade;
- `tools/`: descărcarea (`fetch.py`), citirea buletinelor (`bar_parse.py`), plasarea pe hartă (`locate.py`) și construirea datelor (`build.py`).

Sursa datelor: buletinele B.A.R. publicate de CNCF „CFR” SA. Poziția între stații este aproximativă.

Dr. ing. Iosif Szentes

## Închideri de linie și restricții de manevră (Anexa 19 DRR)

Pagina `ddr.html` arată Anexa 19 a Documentului de Referință al Rețelei CFR („Secții și stații cu restricții de capacitate și manevră”):

- **Circulație** – fiecare închidere de secție este desenată pe traseul ei (secțiile TUI dintre cele două stații), colorată după felul închiderii (totală, un fir, ferestre orare, restricții de viteză, alte) sau după categoria din Legea 202/2016 (A–D). Fereastra fiecărei închideri arată linia, secția, perioada, durata, distanța, categoria și observațiile. Se poate alege data la care se văd închiderile în vigoare, sau cele care încep în următoarele 30/90 de zile; graficul arată numărul de închideri pe luni.
- **Manevră** – stațiile cu restricții de manevră, colorate după operațiile restricționate (descompunere temporară, compunere, atașări/detașări, schimb mijloc de remorcare, linii închise), cu observațiile și notele regionalei.

Anexa se verifică automat la aceeași rulare ca buletinele (zilele 1, 11, 21): `tools/ddr_fetch.py` descarcă PDF-ul de pe cfr.ro, îl păstrează în ramura `arhiva` (`ddr/<an>/`) numai dacă s-a schimbat, iar `tools/ddr_build.py` produce `data/ddr/<versiune>.json`. Toate versiunile rămân disponibile în selectorul „Versiunea anexei”. Stațiile care nu apar în rețeaua TUI sunt poziționate după OpenStreetMap (`data/statii_osm.json`, `tools/statii_osm.py`).
