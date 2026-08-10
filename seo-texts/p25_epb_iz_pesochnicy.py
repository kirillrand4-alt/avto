# -*- coding: utf-8 -*-
"""Проверка доказательств ЭПБ ИЗ ПЕСОЧНИЦЫ — там, где сервер до реестра не доходит.

Замер частотой, а не одной пробой (правило, которое стоило мне двух поспешных выводов):

    из песочницы  10 проб подряд:  200 девять раз, отказ один   —  9 из 10
    с сервера      5 проб подряд:  ни одного ответа            —  0 из 5

`monitor-pb.ru` жив, но нашему серверу не отвечает. А на нём висит доказательство машины у
**813 фактов из 11 947, и у 210 предприятий это ЕДИНСТВЕННАЯ ссылка**. Пока проверка идёт
только с сервера, эти строки числятся непроверяемыми — хотя проверяются отсюда за секунду.

Здесь та же мерка, что у серверного сторожа, но выполненная из песочницы:

    открылась ли страница             (иначе — «не прочёл прибор», а не «нет доказательства»)
    стоит ли на ней НАША машина       по словарю видов
    названо ли предприятие            по ИНН или по собственным словам названия
    цитата                            кусок текста вокруг совпадения — глазами видно, что нашли

ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ: выдуманный номер заключения. Если по нему «доказано» — мерка врёт,
и числа не печатаются как истина.

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import random
import re
import ssl
import sys
import threading
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from p25_imya_predpriyatiya import imya_iz, nazvano  # noqa: E402

SCRATCH = os.environ.get('P25_SCRATCH', '.')
POTOKI = ['park_ingest_3.jsonl', 'park_ingest_3b.jsonl', 'park_ingest_3c.jsonl',
          'park_ingest_3d.jsonl']
VYHOD = os.path.join(SCRATCH, 'PARK-EPB-PROVERENO-IZ-PESOCHNICY-3S.jsonl')
SKOLKO = int(os.environ.get('P25_SKOLKO', '120'))
POTOKOV = int(os.environ.get('P25_POTOKOV', '4'))
PAUZA = float(os.environ.get('P25_PAUZA', '0'))
KONTROL = 'https://monitor-pb.ru/conclusion/99-ЩЩ-99999-2099'
MASH = re.compile(r'компрессор|воздуходув|нагнетател|осушител|азотн|кислородн|'
                  r'воздухоразделит|ГПА', re.I)
TEG = re.compile(r'<(script|style)[^>]*>.*?</\1>|<[^>]+>', re.S | re.I)
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
net = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def tekst(u):
    """Видимый текст страницы. Пусто — значит прибор не прочёл, а не «доказательства нет»."""
    try:
        rq = urllib.request.Request(u, headers={'User-Agent': UA, 'Accept-Language': 'ru'})
        syr = net.open(rq, timeout=40).read(400000).decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        return '', str(e)[:40]
    return re.sub(r'\s+', ' ', TEG.sub(' ', syr)), ''


def citata(t, obrazec, dlina=150):
    i = t.upper().find(obrazec.upper())
    if i < 0:
        return ''
    return t[max(0, i - 60):i + dlina].strip()


# ПОВТОР ИДЁТ ПО ОСТАТКУ, А НЕ ЗАНОВО. Первый заход прочёл 344 из 768 целей, остальные 356
# оборвались с «Connection reset» — хост режет темп при четырёх потоках. Если просто пустить
# скрипт снова, жребий выдаст ту же случайную выборку, файл перезапишется, и уже проверенное
# будет проверено второй раз, а остаток так и останется нетронутым. Поэтому: читаю прежний
# результат, складываю в `uzhe`, беру только НЕПРОВЕРЕННЫЕ, дописываю к прежним.
uzhe = {}
if os.path.exists(VYHOD):
    for s in io.open(VYHOD, encoding='utf-8'):
        try:
            z = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        uzhe[(z.get('inn'), z.get('ssylka'))] = z

celi = []
vidno = set()
for f in POTOKI:
    put = os.path.join(SCRATCH, f)
    if not os.path.exists(put):
        continue
    for s in io.open(put, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        us = [u for u in str(o.get('istochniki') or '').split(' | ') if u.startswith('http')]
        mp = [u for u in us if 'monitor-pb' in u]
        if not mp or len(mp) != len(us):
            continue          # берём только те, где реестр — ЕДИНСТВЕННОЕ доказательство
        k = (o.get('inn'), mp[0])
        if k in vidno:
            continue
        vidno.add(k)
        if k in uzhe:
            continue          # уже прочитано прошлым заходом — не трогаю
        celi.append((o, mp[0]))
random.seed(int(os.environ.get('P25_ZHREBIY', '1234')))
random.shuffle(celi)
ostatok = len(celi)
celi = celi[:SKOLKO]

zamok = threading.Lock()
ochered = list(celi)
gotovo, sch = [], collections.Counter()


def rabotnik():
    while True:
        with zamok:
            if not ochered:
                return
            o, u = ochered.pop()
        time.sleep(PAUZA)     # хост оборвал 356 страниц из 768 при четырёх потоках без пауз
        t, oshibka = tekst(u)
        if not t:
            # ОШИБКА ОДНОЙ СТРАНИЦЫ НЕ ДОЛЖНА УБИВАТЬ ПОТОК. Первый заход дал «проверено 4»
            # при 768 целях: здесь стояло `return`, и каждый из четырёх потоков умирал на
            # своей первой неудачной странице. Тот же класс, что «счётчик до заслона»:
            # ошибка обработки одной строки прекращала обработку всех остальных.
            with zamok:
                sch['не прочёл прибор: %s' % (oshibka or 'пусто')[:30]] += 1
            continue
        est_m = bool(MASH.search(t))
        imya = imya_iz(o)
        est_p, chem = nazvano(imya, o.get('inn'), t)
        with zamok:
            if est_m and est_p:
                sch['ДОКАЗЫВАЕТ: машина и предприятие'] += 1
            elif est_m:
                sch['машина есть, предприятие не названо'] += 1
            else:
                sch['страница открылась, машины нет'] += 1
            gotovo.append({'inn': o.get('inn'), 'predpriyatie': imya[:120],
                           'vid': o.get('vid', ''), 'ssylka': u,
                           'mashina_na_stranice': est_m, 'predpriyatie_na_stranice': est_p,
                           'chem_predpriyatie': chem,
                           'citata_mashiny': citata(t, (MASH.search(t).group(0) if est_m
                                                        else ''))[:220],
                           'kto': '3-я сессия, проверка ЭПБ из песочницы'})


niti = [threading.Thread(target=rabotnik) for _ in range(POTOKOV)]
for n in niti:
    n.start()
for n in niti:
    n.join()

kt, _ = tekst(KONTROL)
kontrol_probit = bool(kt) and bool(MASH.search(kt))

# прежние строки + новые: файл НАКАПЛИВАЕТ, а не заменяет
for z in gotovo:
    uzhe[(z.get('inn'), z.get('ssylka'))] = z
with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for z in uzhe.values():
        f.write(json.dumps(z, ensure_ascii=False) + '\n')
try:
    rq = urllib.request.Request('%s/%s' % (drop, os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT', headers=tok)
    vyl = op.open(rq, timeout=300).read().decode('utf-8', 'replace')[:70]
except Exception as e:  # noqa: BLE001
    vyl = 'НЕ ВЫЛОЖЕНО: %s' % str(e)[:50]

print('\n\n########## ПО ОДНОЙ, ПЕРВЫЕ ВОСЕМЬ')
for z in gotovo[:8]:
    print('  %-12s %-30s %s' % (z['inn'], z['predpriyatie'][:30],
                                'ДОКАЗЫВАЕТ' if z['mashina_na_stranice'] and
                                z['predpriyatie_na_stranice'] else 'нет'))
    if z['citata_mashiny']:
        print('        %s' % z['citata_mashiny'][:110])
print('\n########## ЧИСЛА')
print('  фактов, где реестр — единственное доказательство: %d' % len(vidno))
print('  было прочитано прежними заходами                  %d' % (len(uzhe) - len(gotovo)))
print('  оставалось непрочитанных до этого захода          %d' % ostatok)
print('  прочитано ЗА ЭТОТ заход                           %d' % len(gotovo))
print('  ВСЕГО в накопительном файле                       %d' % len(uzhe))
for k, v in sch.most_common():
    print('     %-52s %5d' % (k[:52], v))
print('  ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ (выдуманный номер): %s'
      % ('машины не нашлось — мерка умеет говорить нет' if not kontrol_probit
         else 'НАШЛАСЬ МАШИНА НА ВЫДУМАННОМ НОМЕРЕ — МЕРКА ВРЁТ'))
print('  выложено: %s' % vyl)
dokaz_vsego = sum(1 for z in uzhe.values()
                  if z.get('mashina_na_stranice') and z.get('predpriyatie_na_stranice'))
print('  ДОКАЗЫВАЮТ всего в файле                          %d' % dokaz_vsego)
print('ИТОГ ' + json.dumps({'целей': len(vidno), 'за заход': len(gotovo),
                            'всего прочитано': len(uzhe), 'доказывают всего': dokaz_vsego,
                            'контроль пробит': bool(kontrol_probit)}, ensure_ascii=False))
