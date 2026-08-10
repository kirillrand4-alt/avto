# -*- coding: utf-8 -*-
"""590 новых ИНН из ЕИС лежат в потоках и НЕ доходят до списков. Ввожу их в парк.

Дыра, которую видно только по числам рядом: за ночь ЕИС дал 590 новых предприятий с
доказанной машиной, а оба готовых списка по-прежнему считают парк равным 1 185. Причина
простая и целиком моя: списки читают `park_ingest_3*.jsonl`, а новые ИНН лежат в
`PARK-EIS-*-PODTV-3S.jsonl`. Добытое, но не введённое в оборот — то же самое, что
недобытое.

Здесь эти потоки превращаются в четвёртый файл парка, `park_ingest_3d.jsonl`, того же
вида, что и первые три: одна строка = один факт «у предприятия есть машина», с видом
машины и со ссылками.

ЗАСЛОНЫ, все три уже стоили ошибок и потому повторены здесь буквально:

  1. слово запроса обязано стоять в ПРЕДМЕТЕ закупки, а не где-то на карточке. Иначе
     в парк попадёт «Проведение этнологической экспертизы» ПАО «Газпром…», где слово
     нашлось в соседнем поле. Сравнение голое: ЕИС вставляет пробелы внутрь слов для
     подсветки («компрессор а», «станц ии»).
  2. организатор торгов машиной не владеет: агентства и департаменты госзаказа, комитеты
     по закупкам, уполномоченные органы — вон, с названной причиной.
  3. ссылка обязательна. Факт без первоисточника в парк не идёт — правило владельца.

ВИД МАШИНЫ БЕРЁТСЯ ИЗ ПРЕДМЕТА, а не из слова запроса: по запросу «компрессорная станция»
может приехать «поставка воздуходувки», и записывать надо то, что в предмете.

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import urllib.request

OPS = r'C:\sender\_ops'
VHODY = ['PARK-EIS-GLUBOKO-PODTV-3S.jsonl', 'PARK-EIS-GLUBOKO-C-PODTV-3S.jsonl',
         'PARK-EIS-GODY-PODTV-3S.jsonl', 'PARK-EIS-GODY2-PODTV-3S.jsonl',
         'PARK-EIS-TURBO-PODTV-3S.jsonl',
         'PARK-EIS-O2VD-PODTV-3S.jsonl',
         'PARK-EIS-KOMPR2022-PODTV-3S.jsonl',
         'PARK-EIS-TIK2-PODTV-3S.jsonl',
         'PARK-EIS-TIK3-PODTV-3S.jsonl',
         'PARK-EIS-TIK4-PODTV-3S.jsonl',
         # РТС-тендер: канал был закрыт моим прибором (верил коду 503, а страница рисуется).
         # ИНН стоит прямо в адресе организатора — самый дешёвый ИНН из всех каналов.
         'PARK-RTS-PODTV-3S.jsonl']
STARYE = ['park_ingest_3.jsonl', 'park_ingest_3b.jsonl', 'park_ingest_3c.jsonl']
VYHOD = os.path.join(OPS, 'park_ingest_3d.jsonl')
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
POSREDNIK = re.compile(r'агентств\w+ (государственн|муниципальн)|'
                       r'департамент\w* (государственн|муниципальн)|'
                       r'комитет\w* .{0,30}закупк|управлени\w* .{0,30}закупк|'
                       r'центр\w* .{0,20}закупок|уполномоченн\w+ орган', re.I)
# вид машины по предмету: порядок важен, более узкое стоит раньше
VIDY = [('генератор кислорода', r'кислородн\w*(станц|генератор)|генератор\w*кислород|'
                                r'кислородн\w*установ'),
        ('генератор азота', r'азотн\w*(станц|генератор)|генератор\w*азот|азотн\w*установ'),
        ('ВРУ', r'воздухоразделительн'),
        ('ГПА', r'газоперекачивающ|гпа\b'),
        ('нагнетатель', r'нагнетател'),
        ('воздуходувка', r'воздуходув|турбовоздуходув'),
        ('осушитель', r'осушител'),
        ('МКС / передвижная', r'передвижн\w*компрессорн|мобильн\w*компрессорн|пкс\b'),
        ('компрессор', r'компрессор|турбокомпрессор')]
VIDY = [(v, re.compile(r, re.I)) for v, r in VIDY]


def golo(s):
    return re.sub(r'[^а-яёa-z0-9]', '', str(s or '').lower())


def s_dropa(imya):
    try:
        return op.open(urllib.request.Request('%s/%s' % (drop, imya), headers=tok),
                       timeout=240).read().decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        print('  не скачался %s: %s' % (imya, str(e)[:50]))
        return ''


bylo = set()
for p in STARYE:
    put = os.path.join(OPS, p)
    if not os.path.exists(put):
        continue
    for s in io.open(put, encoding='utf-8'):
        try:
            i = json.loads(s).get('inn')
        except Exception:  # noqa: BLE001
            continue
        if i:
            bylo.add(i)

potok, snyato = {}, collections.Counter()
for f in VHODY:
    put = os.path.join(OPS, f)
    syr = (io.open(put, encoding='utf-8').read() if os.path.exists(put) else s_dropa(f))
    if not syr:
        snyato['НЕТ ФАЙЛА: %s' % f] += 1
        continue
    for s in syr.splitlines():
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        inn = str(o.get('inn') or '').strip()
        if not inn.isdigit():
            snyato['ИНН пуст'] += 1
            continue
        pred = str(o.get('predmet') or '')
        gp = golo(pred)
        vid = next((v for v, r in VIDY if r.search(pred)), '')
        if not vid:
            # запасной проход по голой строке: подсветка ЕИС рвёт слова пробелами
            vid = next((v for v, r in VIDY if r.search(gp)), '')
        if not vid:
            snyato['в предмете нет ни одной нашей машины'] += 1
            continue
        zak = str(o.get('zakazchik') or o.get('predpriyatie') or '')
        if POSREDNIK.search(zak):
            snyato['организатор торгов — машиной не владеет'] += 1
            continue
        us = [u for u in str(o.get('istochniki') or '').split(' | ') if u.startswith('http')]
        if not us:
            snyato['ссылки-доказательства нет — в парк не идёт'] += 1
            continue
        k = (inn, vid)
        z = potok.get(k)
        if not z:
            z = potok[k] = {'inn': inn, 'vid': vid, 'predpriyatie': zak[:200],
                            'predmet': pred[:250], 'istochniki': [], 'istochnikov': 0,
                            'novyy_dlya_parka': inn not in bylo,
                            'kto': '3-я сессия, ЕИС по словам, годовые срезы'}
        for u in us:
            if u not in z['istochniki']:
                z['istochniki'].append(u)
        z['istochnikov'] = len(z['istochniki'])
        snyato['принято в парк'] += 1

with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for z in potok.values():
        r = dict(z)
        r['istochniki'] = ' | '.join(z['istochniki'])
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
try:
    rq = urllib.request.Request('%s/%s' % (drop, os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT', headers=tok)
    vyl = op.open(rq, timeout=300).read().decode('utf-8', 'replace')[:90]
except Exception as e:  # noqa: BLE001
    vyl = 'НЕ ВЫЛОЖЕНО: %s' % str(e)[:60]

inn_vse = {z['inn'] for z in potok.values()}
inn_nov = {z['inn'] for z in potok.values() if z['novyy_dlya_parka']}
vidy_sch = collections.Counter(z['vid'] for z in potok.values())
dve = sum(1 for z in potok.values() if len(z['istochniki']) > 1)
print('\n\n########## ПЕРВЫЕ ДЕСЯТЬ НОВЫХ')
for z in [x for x in potok.values() if x['novyy_dlya_parka']][:10]:
    print('  %-12s %-18s %s' % (z['inn'], z['vid'][:18], z['predmet'][:66]))
print('\n########## ЧИСЛА')
print('  строк в парковом потоке        %5d' % len(potok))
print('  предприятий                    %5d  (НОВЫХ для парка %d)' % (len(inn_vse),
                                                                      len(inn_nov)))
print('  строк с двумя и более ссылками %5d' % dve)
print('  --- по виду машины')
for k, v in vidy_sch.most_common():
    print('     %-24s %5d' % (k, v))
print('  --- что снято и почему')
for k, v in snyato.most_common():
    print('     %-52s %5d' % (k[:52], v))
print('  файл: %s' % VYHOD)
print('  выложено: %s' % vyl)
print('ИТОГ ' + json.dumps({'строк': len(potok), 'предприятий': len(inn_vse),
                            'новых': len(inn_nov)}, ensure_ascii=False))
