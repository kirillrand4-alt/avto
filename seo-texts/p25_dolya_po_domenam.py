# -*- coding: utf-8 -*-
"""Доля доказанных ССЫЛОК ПО КАЖДОМУ ДОМЕНУ. Два жребия подряд «5 из 5» — повод проверить.

Жребии 3690 и 7051 дали по пять из пяти, и это не повод радоваться: оба раза выборка легла
на `monitor-pb`, домен, который с сервера открывается стабильно. Пять случайных строк — это
проверка ДАННЫХ, но она же нечаянно проверяет и доступность домена, а домены у меня разные:
`tender.pro` режет темп, `zakupki.mos.ru` рисует скриптом, ЭТП ГПБ показывает капчу.

Поэтому меряю иначе: беру ПО КАЖДОМУ крупному домену свою выборку и печатаю долю отдельно.
Тогда видно, где слабое место — в данных или в доступе.

Три исхода на строку, как в замере сторожа:
    ДОКАЗЫВАЕТ   на странице есть и машина, и предприятие (ИНН либо имя)
    ЧАСТИЧНО     машина есть, предприятия не видно
    НЕ ДАЛА      не открылась или машины нет

Числа в КОНЦЕ.
"""
import collections, io, json, os, random, re, ssl, urllib.request
OPS = r'C:\sender\_ops'
POTOKI = ['park_ingest_3.jsonl', 'park_ingest_3b.jsonl', 'park_ingest_3c.jsonl',
          'park_ingest_3d.jsonl']
NA_DOMEN = 6
KRUPNYH = 8
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
net = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                  urllib.request.ProxyHandler({}))
TEG = re.compile(r'<(script|style)[^>]*>.*?</\1>|<[^>]+>', re.S | re.I)
MASH = re.compile(r'компрессор|воздуходув|нагнетател|ГПА|осушител|азот|кислород|ВРУ', re.I)

stroki = []
for f in POTOKI:
    p = os.path.join(OPS, f)
    if not os.path.exists(p):
        continue
    for s in io.open(p, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:
            continue
        us = [u for u in str(o.get('istochniki') or '').split(' | ') if u.startswith('http')]
        if us and o.get('inn'):
            stroki.append((o, us))

def domen(u):
    return re.sub(r'^https?://(?:www\.)?([^/]+).*', r'\1', u).lower()

po_domenu = collections.defaultdict(list)
for o, us in stroki:
    po_domenu[domen(us[0])].append((o, us[0]))
krupnye = [d for d, v in sorted(po_domenu.items(), key=lambda x: -len(x[1]))[:KRUPNYH]]
random.seed(555)
itog = {}
for d in krupnye:
    obr = random.sample(po_domenu[d], min(NA_DOMEN, len(po_domenu[d])))
    sch = collections.Counter()
    for o, u in obr:
        try:
            with net.open(urllib.request.Request(u, headers={'User-Agent': UA,
                                                             'Accept-Language': 'ru'}),
                          timeout=40) as rs:
                t = re.sub(r'\s+', ' ', TEG.sub(' ', rs.read(400000).decode('utf-8', 'replace')))
        except Exception as e:
            sch['НЕ ДАЛА (%s)' % str(e)[:18]] += 1
            continue
        est_m = bool(MASH.search(t))
        est_p = o['inn'] in re.sub(r'\D', '', t)
        if not est_p and o.get('predpriyatie'):
            korni = [w for w in re.findall(r'[А-ЯЁA-Z]{7,}', o['predpriyatie'].upper())]
            est_p = bool(korni) and any(k in t.upper() for k in korni[:2])
        sch['ДОКАЗЫВАЕТ' if (est_m and est_p) else ('ЧАСТИЧНО' if est_m else 'НЕ ДАЛА (нет машины)')] += 1
    itog[d] = (len(po_domenu[d]), sch)

print('\n\n########## ДОЛЯ ДОКАЗАННЫХ ПО ДОМЕНАМ')
print('  %-26s %7s %7s %9s %9s' % ('домен', 'строк', 'проб', 'доказ.', 'частично'))
vsego_d = vsego_p = 0
for d in krupnye:
    n, sch = itog[d]
    prob = sum(sch.values())
    dok = sch['ДОКАЗЫВАЕТ']
    vsego_d += dok; vsego_p += prob
    print('  %-26s %7d %7d %9d %9d   %s'
          % (d[:26], n, prob, dok, sch['ЧАСТИЧНО'],
             ' | '.join('%s %d' % (k, v) for k, v in sch.items() if k.startswith('НЕ ДАЛА'))))
print('\n########## ЧИСЛА')
print('  строк с ссылкой всего      %6d' % len(stroki))
print('  доменов крупных            %6d' % len(krupnye))
print('  проверено ссылок           %6d, доказывают %d (%.0f%%)'
      % (vsego_p, vsego_d, 100.0 * vsego_d / max(1, vsego_p)))
print('ИТОГ ' + json.dumps({d: {'строк': itog[d][0], 'доказ': itog[d][1]['ДОКАЗЫВАЕТ'],
                                'проб': sum(itog[d][1].values())} for d in krupnye},
                           ensure_ascii=False))
