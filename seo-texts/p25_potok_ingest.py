# -*- coding: utf-8 -*-
"""ПОТОК `park_ingest_3.jsonl` — мой долг 1-й сессии. Факт на ПРЕДПРИЯТИЕ, а не на серию.

Почему словаря оказалось мало. 1-я сессия влила мой словарь и честно записала результат:

    «681 серия, 1 361 ссылка. Но КЛАСС ПРОСТАВЛЕН 142 ФАКТАМ НА 20 ИНН. Причина: серии
     записаны как «К-500-61-1», «ЦК-135/8», а в фактах марка лежит как «4ВМ10-100/8» —
     совпадение по НАЧАЛУ СТРОКИ срабатывает редко.»

Диагноз верный, и починка на моей стороне, а не на её: словарь — это агрегат по серии, у
него нет колонки ИНН вовсе (есть только `innov`, ЧИСЛО предприятий). Соседу приходилось
восстанавливать связь «серия → предприятие» сшивкой строк, и она рвалась на форме записи.

Отдаю не агрегат, а сам поток: одна запись = одно (ИНН, серия), уже со всеми ссылками.
Сшивать ничего не надо, форма записи больше не решает.

ТРИ ВЕЩИ, КОТОРЫХ В СЛОВАРЕ НЕ БЫЛО

1. ВСЕ ЧЕТЫРЕ ВЕТКИ НОМЕНКЛАТУРЫ, а не одни центробежные. Владелец поймал всех троих:
   «почему вы разбираете факты только те которые скачали по центробежникам? задача ВСЕ
   компрессоры + МКС + генераторы азота/кислорода». Беру оба своих шаблона серий —
   центробежный и не-центробежный (импорт GA/GX/ZR/SSR/BSD, отечественные ВК/ПКС/НВЭ,
   МКС/ПКС/ЗИФ-ПВ, азот-кислород АГ/АДС/ТГА/КГС) — и добавляю четвёртым источником боевую
   `enrich.db`, где лежит вся номенклатура, а не выгрузка по центробежникам.

2. ПРОВЕНАНС НАКАПЛИВАЕТСЯ. Правило владельца: «если ссылок несколько = должно быть
   несколько ссылок в базе». Складываю ВСЕ разные ссылки (не первые три, как в словаре) и
   пишу рядом их число и список баз-таблиц, где факт встретился. Подтверждённое дважды
   обязано быть отличимо от подтверждённого однажды.

3. КЛЮЧ СШИВКИ ЛЕЖИТ В САМОЙ ЗАПИСИ. Поле `klyuch` — это написание без пробелов и дефисов
   в верхнем регистре («К-250-61-5» → «К250.61.5»). Сосед джойнит по нему, а не по началу
   строки. Форма записи перестаёт быть препятствием.

ЗАСЛОНЫ — все оплаченные, ни одного нового на веру:
   разметка самой строки («машина лишь упомянута», «объект — трубопровод или сооружение»),
   позиция/зав.№ перед обозначением, чужая машина в окне, вердикт провайдера «не наша».
   Плюс новый и обязательный по правилу владельца: ФАКТ БЕЗ ССЫЛКИ В ПОТОК НЕ ИДЁТ —
   он считается отдельно и печатается, чтобы размер потери был виден.

ИНН беру двумя путями и НАЗЫВАЮ, каким именно: из колонки базы либо из текста, но только
там, где перед числом стоит слово ИНН. Число, стоящее само по себе, за ИНН не считаю.

Только чтение. Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import sqlite3
import urllib.request

ISTOCHNIKI = [(r'C:\sender\enrich.db', 'signals'),
              (r'C:\seostat\data\centrifugal.db', 'fact'),
              (r'C:\seostat\drop\drop-storage\atlas_copco.db', 'tenders'),
              (r'C:\seostat\drop\drop-storage\atlas_copco.db', 'fakty')]
RAZOBRANY = r'C:\sender\_ops\PARK-SLOVAR-SERII-RAZOBRANY-3S.json'
VYHOD = r'C:\sender\_ops\park_ingest_3.jsonl'

SEMEYSTVA = [
    ('компрессоры (советские/центробежные)', re.compile(
        r'\b((?:ТВ|ЦК|ЦНД|К|КТК|ВЦ|НВЭ|ВП|ВМ|ЭК|АК|ГПА|ВШ|Ц)'
        r'[- ]?\d{1,4}(?:[-/][\dА-Яа-яA-Za-z,\.]{1,8}){0,3})\b', re.U)),
    ('компрессоры (импорт винтовые)', re.compile(
        r'\b((?:GA|GX|GR|ZR|ZT|ZE|XAS|XAHS|SSR|BSD|CSD|ASD|SK|KE|FST|SF)'
        r'[- ]?\d{1,4}(?:[- ]?(?:VSD|FF|AP|VS))?)\b')),
    ('компрессоры (отечественные винт/поршень)', re.compile(
        r'\b((?:ВК|ВВ|ПКСД|АКР|СО)[- ]?\d{1,3}[А-Яа-яA-Za-z]?'
        r'(?:[-/][\dА-Яа-я,\.]{1,6}){0,2})\b', re.U)),
    ('МКС / передвижные', re.compile(
        r'\b((?:МКС|ЗИФ-ПВ|ДЭН|ПКС|КВ)[- ]?\d{1,3}(?:[-/][\d,\.]{1,6}){0,2})\b', re.U)),
    ('азот / кислород', re.compile(
        r'\b((?:АГ|АДС|ТГА|ААР|КГС|КЖ|СКДС|УКА|ГА|ГК|АКМ|ТКА)[- ]?\d{1,4}'
        r'(?:[-/][\dА-Яа-я,\.]{1,6}){0,2})\b', re.U)),
]
POMETKA_NE_MASHINA = re.compile(
    r'объект\s*[—-]\s*трубопровод\s+или\s+сооружение|машина\s+лишь\s+упомянута|'
    r'не\s+применимо|тип\s+не\s+установлен\s+среда\s+не\s+названа', re.I)
PRINCIP = (('центробежный', re.compile(r'центробежн|турбокомпрессор', re.I)),
           ('винтовой', re.compile(r'винтов', re.I)),
           ('поршневой', re.compile(r'поршнев', re.I)),
           ('мембранный/адсорбционный', re.compile(r'мембранн|адсорбцион|\bPSA\b', re.I)))
VID = (('воздуходувка', re.compile(r'воздуходув|газодув', re.I)),
       ('нагнетатель', re.compile(r'нагнетател', re.I)),
       ('ВРУ', re.compile(r'воздухоразделен|\bВРУ\b|криоген', re.I)),
       ('генератор азота', re.compile(r'генератор\w*\s+азота|азотн\w+\s+станци|'
                                      r'мембранн\w+\s+азот|азотн\w+\s+установк', re.I)),
       ('генератор кислорода', re.compile(r'генератор\w*\s+кислорода|кислородн\w+\s+станци|'
                                          r'концентратор\w*\s+кислорода|кислородн\w+\s+установк', re.I)),
       ('МКС / передвижная', re.compile(r'\bМКС\b|передвижн\w+\s+компрессор|'
                                        r'мобильн\w+\s+компрессор|дизельн\w+\s+компрессор', re.I)),
       ('осушитель', re.compile(r'осушител', re.I)),
       ('ГПА', re.compile(r'газоперекачивающ|\bГПА\b', re.I)),
       ('компрессор', re.compile(r'\bкомпрессор', re.I)))
CHUZH = re.compile(r'вентилятор|дымосос|\bнасос\w*\b|градирн|кондиционер|трактор|сельхоз|'
                   r'автотранспорт|стартер|автомат\w*\s+выключател|\bIP\d\d\b|'
                   r'золотоизвлекательн|турбогенератор|турбоагрегат|турбовальн|\bМи-8\b|'
                   r'адсорбер|абсорбер|паропровод|\bЦВД\b|\bЦНД\b|\bЦСД\b', re.I)
POZ = re.compile(r'поз\.?\s*$|позици\w*\s*$|№\s*$|техн\.?\s*№\s*$|зав\.?\s*№\s*$', re.I)
INN_RYADOM = re.compile(r'ИНН\D{0,4}(\d{10}|\d{12})\b', re.I)
URL = re.compile(r'https?://[^\s"\'<>|;]+')
# ось цены: чем дороже машина, тем ценнее предприятие владельцу
KLASS = {'ГПА': 5, 'компрессор': 4, 'нагнетатель': 4, 'ВРУ': 4, 'генератор азота': 4,
         'генератор кислорода': 4, 'воздуходувка': 3, 'МКС / передвижная': 3, 'осушитель': 2}


def klyuch(s):
    return re.sub(r'[\s\-]', '', s).upper().replace(',', '.')


prov = {}
if os.path.exists(RAZOBRANY):
    try:
        for o in json.loads(io.open(RAZOBRANY, encoding='utf-8').read()):
            prov[klyuch(o.get('seriya') or '')] = o
    except Exception:  # noqa: BLE001
        pass

zapisi = collections.defaultdict(lambda: {'v': 0, 'p': collections.Counter(),
                                          'vid': collections.Counter(), 'url': set(),
                                          'iz': set(), 'napis': set(), 'cit': '',
                                          'sem': collections.Counter(),
                                          'inn_kak': collections.Counter()})
snyato = collections.Counter()
strok_vsego = 0
for baza, tabl in ISTOCHNIKI:
    if not os.path.exists(baza):
        snyato['база не найдена: %s' % baza] += 1
        continue
    try:
        cx = sqlite3.connect('file:%s?mode=ro' % baza.replace('\\', '/'), uri=True)
        kol = [r[1] for r in cx.execute('pragma table_info("%s")' % tabl)]
    except Exception as e:  # noqa: BLE001
        snyato['таблица не открылась %s/%s: %s' % (os.path.basename(baza), tabl, str(e)[:40])] += 1
        continue
    if not kol:
        cx.close()
        continue
    pinn = 'inn' if 'inn' in kol else ('company_inn' if 'company_inn' in kol else None)
    metka = '%s/%s' % (os.path.basename(baza), tabl)
    for r in cx.execute('select %s from "%s"' % (','.join('"%s"' % k for k in kol), tabl)):
        strok_vsego += 1
        d = dict(zip(kol, r))
        tekst = ' '.join(str(v) for v in r if v is not None)
        if len(tekst) < 8:
            continue
        if POMETKA_NE_MASHINA.search(tekst):
            snyato['разметка строки: машина лишь упомянута / не применимо'] += 1
            continue
        # ИНН строки — с указанием, откуда он взят
        inn, inn_kak = '', ''
        if pinn and str(d.get(pinn) or '').strip().isdigit():
            inn, inn_kak = str(d[pinn]).strip(), 'колонка %s' % pinn
        else:
            m = INN_RYADOM.search(tekst)
            if m:
                inn, inn_kak = m.group(1), 'текст рядом со словом ИНН'
        if not inn:
            snyato['ИНН у строки нет — предприятие не названо'] += 1
            continue
        ssylki = set(URL.findall(tekst))
        if not ssylki:
            snyato['ссылки-доказательства нет — по правилу владельца в поток не идёт'] += 1
            continue
        for sem, rg in SEMEYSTVA:
            for m in rg.finditer(tekst):
                syr = m.group(1)
                do = tekst[max(0, m.start() - 60):m.start()]
                okno = tekst[max(0, m.start() - 130):m.end() + 130]
                if POZ.search(do):
                    snyato['позиция / техн. № / зав. №'] += 1
                    continue
                if CHUZH.search(okno):
                    snyato['чужая машина / чужой предмет в окне'] += 1
                    continue
                k = klyuch(syr)
                if prov.get(k) and not prov[k].get('nashe'):
                    snyato['вердикт провайдера: не наша машина'] += 1
                    continue
                z = zapisi[(inn, k)]
                z['v'] += 1
                z['napis'].add(syr)
                z['sem'][sem] += 1
                z['iz'].add(metka)
                z['inn_kak'][inn_kak] += 1
                z['url'] |= ssylki
                for i, rg2 in PRINCIP:
                    if rg2.search(okno):
                        z['p'][i] += 1
                        break
                for i, rg2 in VID:
                    if rg2.search(okno):
                        z['vid'][i] += 1
                        break
                if not z['cit']:
                    z['cit'] = re.sub(r'[\s;]+', ' ', okno)[:200]
    cx.close()

# в поток идёт только то, у чего вид машины ДОКАЗАН текстом
potok = []
for (inn, k), z in zapisi.items():
    vid = (z['vid'].most_common(1) or [('', 0)])[0][0]
    if not vid:
        snyato['вид машины текстом не доказан'] += 1
        continue
    ss = sorted(z['url'])
    potok.append({
        'inn': inn,
        'klyuch': k,
        'napisanie': ' | '.join(sorted(z['napis'])[:4]),
        'vid': vid,
        'princip': (z['p'].most_common(1) or [('не установлен', 0)])[0][0],
        'vetka': (z['sem'].most_common(1) or [('', 0)])[0][0],
        'klass_ceny': KLASS.get(vid, 2),
        'vstrech': z['v'],
        'istochniki': ' | '.join(ss),
        'istochnikov': len(ss),
        'dokazano_iz': ' | '.join(sorted(z['iz'])),
        'dokazano_iz_skolko': len(z['iz']),
        'inn_otkuda': ' | '.join(sorted(z['inn_kak'])),
        'citata': z['cit'],
        'kto': '3-я сессия, park_ingest_3',
    })
potok.sort(key=lambda o: (-o['istochnikov'], -o['vstrech']))
with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for o in potok:
        f.write(json.dumps(o, ensure_ascii=False) + '\n')

# ПРОБА: у каждой десятой записи потока ссылка обязана быть похожа на адрес документа,
# а обозначение — стоять в цитате. Если не так, значит я склеила не то.
provaly = []
for o in potok[::max(1, len(potok) // 10)][:10]:
    if not o['istochniki'].startswith('http'):
        provaly.append('%s %s: ссылка не адрес' % (o['inn'], o['napisanie']))
    elif not any(klyuch(n) in klyuch(o['citata']) for n in o['napisanie'].split(' | ')):
        provaly.append('%s %s: обозначения нет в цитате' % (o['inn'], o['napisanie']))

vylozheno = 'не выкладывала'
try:
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'),
                                            os.path.basename(VYHOD)),
                                 data=io.open(VYHOD, 'rb').read(), method='PUT',
                                 headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    vylozheno = op.open(req, timeout=300).read().decode('utf-8', 'replace')[:110]
except Exception as e:  # noqa: BLE001
    vylozheno = 'не выложено: %s' % str(e)[:90]

vetki = collections.Counter(o['vetka'] for o in potok)
vidy = collections.Counter(o['vid'] for o in potok)
inn_mnogo = sum(1 for o in potok if o['istochnikov'] >= 2)
print('\n\n########## ПРОБА')
for p in provaly:
    print('  ПРОВАЛ: %s' % p)
print('  провалов %d из 10' % len(provaly))
print('\n########## ПРИМЕРЫ (первые три записи потока)')
for o in potok[:3]:
    print('  %s  %-22s %-20s ссылок %d  из %s' % (o['inn'], o['napisanie'][:22], o['vid'],
                                                  o['istochnikov'], o['dokazano_iz']))
    print('     %s' % o['citata'][:150])
print('\n########## ЧИСЛА')
print('  строк прочитано        %8d' % strok_vsego)
print('  записей в потоке       %8d' % len(potok))
print('  разных ИНН             %8d' % len({o['inn'] for o in potok}))
print('  у скольких 2+ ссылки   %8d' % inn_mnogo)
print('  --- по ветке номенклатуры')
for k, v in vetki.most_common():
    print('     %-42s %6d' % (k, v))
print('  --- по виду машины')
for k, v in vidy.most_common():
    print('     %-42s %6d' % (k, v))
print('  --- сняли заслоны')
for k, v in snyato.most_common(12):
    print('     %-56s %8d' % (k[:56], v))
print('  файл: %s' % VYHOD)
print('  выложено: %s' % vylozheno)
print('ИТОГ ' + json.dumps({'записей': len(potok), 'ИНН': len({o['inn'] for o in potok}),
                            'с 2+ ссылками': inn_mnogo, 'провалов пробы': len(provaly)},
                           ensure_ascii=False))
