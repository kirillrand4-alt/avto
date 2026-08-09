# -*- coding: utf-8 -*-
"""СЛОВАРЬ, четвёртый заход. Заслон беру ИЗ ДАННЫХ, а не из своего окна ±130 знаков.

Третий заход провалил пробу 5 из 10, и цитаты показали причину — она одна на все пять:

    К-105  «есть К-102 | К-103 | К-104 | К-105  ОБЪЕКТ — ТРУБОПРОВОД ИЛИ СООРУЖЕНИЕ,
            МАШИНА ЛИШЬ УПОМЯНУТА  среда не названа»

**Пометка уже стоит в самой строке базы.** Прошлый разбор её проставил, а я её не читала и
пыталась вывести то же самое своим окном вокруг обозначения. Окно проигрывает: у ЗИФ-1
слово «золотоизвлекательная» оказалось за его границей, у ЗИФ2 рядом стояла «воздуходувка
RRF-350» и мой же признак «наша машина рядом» отменил заслон — хотя воздуходувка стоит НА
фабрике, а ЗИФ2 это цех, а не серия.

Правило: если данные уже содержат разметку, читать её, а не выводить заново.

ВТОРОЙ ИСТОЧНИК ЗАСЛОНА — провайдер. Он разобрал 130 неясных серий и сказал:

    наше=False 110 из 130 | «не наша машина» 71 | «непонятно» 42 | наше=True 20

Сорок два «непонятно» — это заслон от самообмана сработал: модель не угадывала. Её вердикты
беру как отдельный источник и печатаю, сколько серий сняла именно она.
"""
import collections
import io
import json
import os
import re
import sqlite3
import urllib.request

ISTOCHNIKI = [(r'C:\seostat\data\centrifugal.db', 'fact'),
              (r'C:\seostat\drop\drop-storage\atlas_copco.db', 'tenders'),
              (r'C:\seostat\drop\drop-storage\atlas_copco.db', 'fakty')]
RAZOBRANY = r'C:\sender\_ops\PARK-SLOVAR-SERII-RAZOBRANY-3S.json'
SERIYA = re.compile(
    r'\b((?:ТВ|ЦК|ЦНД|К|КТК|ВЦ|ЗИФ|НВЭ|ВП|ВМ|ПКС|ЭК|АК|ТГ|ГПА|АДГ|ВК|КР|УКС|ВШ|ТКА|Ц)'
    r'[- ]?\d{1,4}(?:[-/][\dА-Яа-яA-Za-z,\.]{1,8}){0,3})\b', re.U)
# ЗАСЛОН ИЗ ДАННЫХ: разметка прошлого разбора, стоящая в самой строке
POMETKA_NE_MASHINA = re.compile(
    r'объект\s*[—-]\s*трубопровод\s+или\s+сооружение|машина\s+лишь\s+упомянута|'
    r'не\s+применимо|тип\s+не\s+установлен\s+среда\s+не\s+названа', re.I)
PRINCIP = (('центробежный', re.compile(r'центробежн|турбокомпрессор', re.I)),
           ('винтовой', re.compile(r'винтов', re.I)),
           ('поршневой', re.compile(r'поршнев', re.I)),
           ('мембранный', re.compile(r'мембранн', re.I)))
VID = (('воздуходувка', re.compile(r'воздуходув|газодув', re.I)),
       ('нагнетатель', re.compile(r'нагнетател', re.I)),
       ('ВРУ', re.compile(r'воздухоразделен|\bВРУ\b|криоген', re.I)),
       ('генератор азота', re.compile(r'генератор\w*\s+азота|азотн\w+\s+станци', re.I)),
       ('генератор кислорода', re.compile(r'генератор\w*\s+кислорода|кислородн\w+\s+станци', re.I)),
       ('МКС', re.compile(r'\bМКС\b|передвижн\w+\s+компрессор', re.I)),
       ('осушитель', re.compile(r'осушител', re.I)),
       ('ГПА', re.compile(r'газоперекачивающ|\bГПА\b', re.I)),
       ('компрессор', re.compile(r'\bкомпрессор', re.I)))
CHUZH = re.compile(r'вентилятор|дымосос|\bнасос\w*\b|градирн|кондиционер|трактор|сельхоз|'
                   r'автотранспорт|стартер|автомат\w*\s+выключател|\bIP\d\d\b|'
                   r'золотоизвлекательн|турбогенератор|турбоагрегат|турбовальн|\bМи-8\b|'
                   r'адсорбер|абсорбер|паропровод|\bЦВД\b|\bЦНД\b|\bЦСД\b', re.I)
POZ = re.compile(r'поз\.?\s*$|позици\w*\s*$|№\s*$|техн\.?\s*№\s*$|зав\.?\s*№\s*$', re.I)


def klyuch(s):
    return re.sub(r'[\s\-]', '', s).upper().replace(',', '.')


# вердикты провайдера
prov = {}
if os.path.exists(RAZOBRANY):
    for o in json.loads(io.open(RAZOBRANY, encoding='utf-8').read()):
        prov[klyuch(o.get('seriya') or '')] = o

s_ = collections.defaultdict(lambda: {'v': 0, 'p': collections.Counter(),
                                      'vid': collections.Counter(), 'inn': set(),
                                      'url': set(), 'cit': '', 'napis': set()})
snyato = collections.Counter()
for baza, tabl in ISTOCHNIKI:
    if not os.path.exists(baza):
        continue
    cx = sqlite3.connect('file:%s?mode=ro' % baza.replace('\\', '/'), uri=True)
    kol = [r[1] for r in cx.execute('pragma table_info("%s")' % tabl)]
    if not kol:
        cx.close(); continue
    pinn = 'inn' if 'inn' in kol else None
    for r in cx.execute('select %s from "%s"' % (','.join('"%s"' % k for k in kol), tabl)):
        d = dict(zip(kol, r))
        tekst = ' '.join(str(v) for v in r if v is not None)
        if len(tekst) < 8:
            continue
        # ЗАСЛОН ИЗ ДАННЫХ — на всю строку, а не на окно
        if POMETKA_NE_MASHINA.search(tekst):
            snyato['разметка строки: машина лишь упомянута / не применимо'] += 1
            continue
        for m in SERIYA.finditer(tekst):
            syr = m.group(1)
            do = tekst[max(0, m.start() - 60):m.start()]
            okno = tekst[max(0, m.start() - 130):m.end() + 130]
            if POZ.search(do):
                snyato['позиция / техн. № / зав. №'] += 1; continue
            if CHUZH.search(okno):
                snyato['чужая машина / чужой предмет'] += 1; continue
            k = klyuch(syr)
            if prov.get(k) and not prov[k].get('nashe'):
                snyato['вердикт провайдера: не наша машина'] += 1; continue
            z = s_[k]
            z['v'] += 1
            z['napis'].add(syr)
            for i, rg in PRINCIP:
                if rg.search(okno):
                    z['p'][i] += 1; break
            for i, rg in VID:
                if rg.search(okno):
                    z['vid'][i] += 1; break
            if pinn and str(d.get(pinn) or '').strip():
                z['inn'].add(str(d[pinn]).strip())
            for u in re.findall(r'https?://\S+', tekst)[:3]:
                z['url'].add(u)
            if not z['cit']:
                z['cit'] = re.sub(r'[\s;]+', ' ', okno)[:170]
    cx.close()

itog = {k: z for k, z in s_.items() if z['v'] >= 2}
UYTI = ['ЗИФ-1', 'ЗИФ2', 'ТВ2-117А', 'ТГ-1', 'ТГ-2', 'К-105', 'К-108']
OSTATSYA = [('ТВ-80-1,6', 'воздуходувка'), ('К-250-61-1', 'компрессор'), ('ЦК-135/8', 'компрессор')]
provaly = []
for s in UYTI:
    k = klyuch(s)
    if k in itog and itog[k]['v'] > 5:
        provaly.append('%s осталась (%d): %s' % (s, itog[k]['v'], itog[k]['cit'][:80]))
for s, vd in OSTATSYA:
    k = klyuch(s)
    if k not in itog:
        provaly.append('%s ПОТЕРЯНА' % s)
    elif (itog[k]['vid'].most_common(1) or [('?', 0)])[0][0] != vd:
        provaly.append('%s вид: ждали «%s», вышло «%s»'
                       % (s, vd, (itog[k]['vid'].most_common(1) or [('?', 0)])[0][0]))

dok = [(k, z) for k, z in itog.items()
       if (z['vid'].most_common(1) or [('не установлен', 0)])[0][0] != 'не установлен']
put = r'C:\sender\_ops\PARK-SLOVAR-SERII-3S-v4.csv'
with io.open(put, 'w', encoding='utf-8-sig') as f:
    f.write('seriya;napisaniya;princip;vid;vstrech;innov;ssylok;ssylki;citata\n')
    for k, z in sorted(dok, key=lambda x: -x[1]['v']):
        f.write(';'.join([k, ' | '.join(sorted(z['napis'])[:4]),
                          (z['p'].most_common(1) or [('не установлен', 0)])[0][0],
                          (z['vid'].most_common(1) or [('?', 0)])[0][0],
                          str(z['v']), str(len(z['inn'])), str(len(z['url'])),
                          ' | '.join(list(z['url'])[:3]), z['cit'].replace(';', ',')]) + '\n')
try:
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'),
                                            os.path.basename(put)),
                                 data=io.open(put, 'rb').read(), method='PUT',
                                 headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    otvet = op.open(req, timeout=180).read().decode('utf-8', 'replace')[:110]
except Exception as e:  # noqa: BLE001
    otvet = 'не выложено: %s' % str(e)[:90]

print('\n\n########## ПРОБА')
for p in provaly:
    print('  ПРОВАЛ: %s' % p)
print('  провалов %d из %d' % (len(provaly), len(UYTI) + len(OSTATSYA)))
print('\n########## ЧИСЛА')
print('  серий               %5d' % len(itog))
print('  с доказанным видом  %5d' % len(dok))
print('  разных ИНН          %5d' % len({i for _, z in dok for i in z['inn']}))
print('  --- сняли заслоны')
for k, v in snyato.most_common():
    print('     %-56s %6d' % (k, v))
print('  выложено: %s' % otvet)
print('ИТОГ ' + json.dumps({'серий': len(itog), 'доказанных': len(dok),
                            'провалов': len(provaly)}, ensure_ascii=False))
