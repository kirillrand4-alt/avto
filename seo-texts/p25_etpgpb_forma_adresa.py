# -*- coding: utf-8 -*-
"""ЭТП ГПБ: моя прошлая формулировка «простым запросом карточку не увидеть» ОПРОВЕРГНУТА.

Проверка пяти случайных ссылок дала это прямо:

    https://etpgpb.ru/procedure/tender/etp/1273912-tehnicheskoe-obsluzhivanie-po-planu-
    v-to-8000-kompressora-tipa-zr-450-10-50-proizvodstva-atlas-copco-po/   -> ДОКАЗЫВАЕТ

Обычный запрос, без браузера, и обозначение ZR-450 на странице нашлось. Значит дело было не
в гидратации Nuxt, а в МОЕЙ форме адреса: я строила `/procedures/etp/<номер>/`, а рабочая
форма — `/procedure/tender/etp/<номер>-<словесный-хвост>/`. Короткая отдавала 200 на любой
мусор, то есть была мягким 404, и я приняла это за «страницу рисует скрипт».

Проверяю четыре формы на восьми номерах, взятых из РАБОЧИХ ссылок базы (номер там точно
существует). Что откроется и покажет обозначение — та форма и годится для 26 873 строк
`tenders`, которые сейчас лежат без доказательства.

Числа в КОНЦЕ.
"""
import collections
import io
import json
import re
import ssl
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                 urllib.request.ProxyHandler({}))
TEG = re.compile(r'<[^>]+>')
POTOK = r'C:\sender\_ops\park_ingest_3.jsonl'

# берём рабочие ссылки ЭТП ГПБ из потока: номер и хвост оттуда
rabochie = []
for s in io.open(POTOK, encoding='utf-8'):
    o = json.loads(s)
    for u in (o.get('istochniki') or '').split(' | '):
        m = re.search(r'etpgpb\.ru/procedure/tender/etp/(\d+)-([a-z0-9\-]+)/?', u)
        if m:
            rabochie.append((m.group(1), m.group(2), u, o.get('napisanie', '')))
vid = set()
obr = []
for n, hv, u, nap in rabochie:
    if n in vid:
        continue
    vid.add(n)
    obr.append((n, hv, u, nap))
    if len(obr) >= 8:
        break

FORMY = [
    ('полная, как в базе', lambda n, hv: 'https://etpgpb.ru/procedure/tender/etp/%s-%s/' % (n, hv)),
    ('без хвоста', lambda n, hv: 'https://etpgpb.ru/procedure/tender/etp/%s/' % n),
    ('короткая procedures', lambda n, hv: 'https://etpgpb.ru/procedures/etp/%s/' % n),
    ('хвост-заглушка', lambda n, hv: 'https://etpgpb.ru/procedure/tender/etp/%s-x/' % n),
]
itog = collections.defaultdict(lambda: {'ok': 0, 'dlina': [], 'net': 0})
print('########## ПО НОМЕРАМ')
for n, hv, u, nap in obr:
    for imya, f in FORMY:
        adr = f(n, hv)
        try:
            h = op.open(urllib.request.Request(adr, headers={'User-Agent': UA}),
                        timeout=45).read().decode('utf-8', 'replace')
            t = re.sub(r'\s+', ' ', TEG.sub(' ', h))
            est = bool(nap) and any(re.sub(r'[\s\-]', '', x).upper() in
                                    re.sub(r'[\s\-]', '', t).upper()
                                    for x in nap.split(' | ') if len(x) > 3)
            itog[imya]['dlina'].append(len(t))
            if est:
                itog[imya]['ok'] += 1
            print('  %-10s %-20s знаков %6d обозначение %s' % (n, imya, len(t), est))
        except Exception as e:  # noqa: BLE001
            itog[imya]['net'] += 1
            print('  %-10s %-20s НЕ ОТКРЫЛАСЬ %s' % (n, imya, str(e)[:40]))
print('\n########## ЧИСЛА')
for imya, _ in FORMY:
    z = itog[imya]
    dl = z['dlina']
    print('  %-22s обозначение найдено %d из %d | не открылась %d | длина ответа %s'
          % (imya, z['ok'], len(obr), z['net'],
             ('одинаковая %d' % dl[0]) if dl and len(set(dl)) == 1 else 'разная'))
print('ИТОГ ' + json.dumps({imya: itog[imya]['ok'] for imya, _ in FORMY}, ensure_ascii=False))
