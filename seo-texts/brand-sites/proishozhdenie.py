"""Страна производства и производитель винтового блока по сайтам сетки.

Оба поля найдены инвентаризацией 21.08 и до сих пор не читались:
IP_PROP22671 (страна, 22 199 товаров) и IP_PROP22670 (винтовой блок,
12 545 товаров). Это сильнейший технический довод брендовой страницы -
«сердце машины от признанного производителя» - и он у каждого бренда
свой, то есть работает ещё и на разводку.
"""
import csv, json, os, sys, collections
csv.field_size_limit(10 ** 7)

SAYT = {'abac': 'abac-kompressor.ru', 'atlas copco': 'ac-kompressor.ru',
        'berg': 'berg-kompressor.ru', 'cross air': 'crossair-compressor.ru',
        'dali': 'dali-kompressor.ru', 'ekomak': 'ekomak-kompressor.com',
        'enger': 'enger-air.ru', 'fini': 'fini-compressor.com',
        'ironmac': 'ironmac-compressor.com',
        'kraftmann': 'kraftmann-kompressor.com',
        'remeza': 'remeza-kompressor.ru', 'зиф': 'zif-kompressor.ru'}

seen = set()
strana = collections.defaultdict(collections.Counter)
blok = collections.defaultdict(collections.Counter)
for row in csv.DictReader(sys.stdin, delimiter=';'):
    k = (row.get('IE_XML_ID') or '').strip()
    if not k or k in seen:
        continue
    seen.add(k)
    b = (row.get('IP_PROP22553') or '').strip().lower()
    site = next((v for kk, v in SAYT.items() if kk in b), None)
    if not site:
        continue
    s = (row.get('IP_PROP22671') or '').strip()
    if s:
        strana[site][s] += 1
    vb = (row.get('IP_PROP22670') or '').strip()
    if vb:
        blok[site][vb] += 1

itog = {}
for site in set(strana) | set(blok):
    d = {}
    if strana.get(site):
        vs = sum(strana[site].values())
        gl, n = strana[site].most_common(1)[0]
        d['страна'] = {'значение': gl, 'позиций': n, 'из': vs,
                       'доля, %': round(100 * n / vs),
                       'все значения': dict(strana[site].most_common(4))}
    if blok.get(site):
        vs = sum(blok[site].values())
        gl, n = blok[site].most_common(1)[0]
        d['винтовой блок'] = {'значение': gl, 'позиций': n, 'из': vs,
                              'доля, %': round(100 * n / vs),
                              'все значения': dict(blok[site].most_common(5))}
    itog[site] = d

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'proishozhdenie.json')
if len(sys.argv) > 1:
    out = sys.argv[1]
with open(out, 'w', encoding='utf-8') as f:
    json.dump(itog, f, ensure_ascii=False, indent=1)
    f.flush(); os.fsync(f.fileno())
for site, d in sorted(itog.items()):
    s = d.get('страна', {})
    b = d.get('винтовой блок', {})
    print(f"{site:<28} {s.get('значение','-'):<16} "
          f"блок {b.get('значение','-'):<28} {b.get('доля, %','-')}%")
print(f'\n-> {out}')
