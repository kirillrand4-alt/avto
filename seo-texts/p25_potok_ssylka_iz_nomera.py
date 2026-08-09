# -*- coding: utf-8 -*-
"""40 124 строки выпали «нет ссылки». Пробую вернуть их, СОБРАВ ссылку из номера документа.

Первый заход потока дал 1 380 записей на 439 ИНН — и самый крупный заслон оказался не
смысловым, а формальным:

    ссылки-доказательства нет — по правилу владельца в поток не идёт     40 124
    разметка строки: машина лишь упомянута                               12 823
    ИНН у строки нет                                                      3 736

Сорок тысяч строк отброшены не потому, что факта нет, а потому что рядом не лежал адрес.
При этом в цитатах этих же строк стоит ИДЕНТИФИКАТОР ДОКУМЕНТА:

    «заключение ЭПБ № 42-ТУ-896427-2026»

а рабочие ссылки словаря выглядят так:

    https://monitor-pb.ru/conclusion/41-%D0%A2%D0%A3-22396-2019   = «41-ТУ-22396-2019»

То есть адрес — это номер заключения, закодированный для URL. Ссылку можно собрать.

ГДЕ ЗДЕСЬ ОПАСНОСТЬ, и почему без проверки это делать нельзя. Собранная ссылка — это моя
гипотеза, а не добытое доказательство. Если шаблон неверен или страница не существует, я
произведу сорок тысяч фиктивных доказательств, и они будут выглядеть убедительнее честного
пропуска. Правило владельца — ссылка обязана ВЕСТИ на доказательство, а не просто быть
похожей на адрес.

Поэтому порядок такой и другого не будет:
  1. собрать ссылки из номеров;
  2. ОТКРЫТЬ двадцать случайных прямо с сервера и посмотреть три вещи: код ответа, есть ли
     на странице сам номер, есть ли обозначение машины;
  3. и только если доля открывшихся с номером высока — записать поток, пометив каждую
     такую ссылку как «собрана из номера заключения, проверено N из 20», чтобы происхождение
     было видно и через месяц.
  4. если доля низкая — НЕ писать поток вовсе и напечатать, что шаблон не подтвердился.

Только чтение. Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import random
import re
import sqlite3
import ssl
import urllib.parse
import urllib.request

ISTOCHNIKI = [(r'C:\sender\enrich.db', 'signals'),
              (r'C:\seostat\data\centrifugal.db', 'fact'),
              (r'C:\seostat\drop\drop-storage\atlas_copco.db', 'tenders'),
              (r'C:\seostat\drop\drop-storage\atlas_copco.db', 'fakty')]
RAZOBRANY = r'C:\sender\_ops\PARK-SLOVAR-SERII-RAZOBRANY-3S.json'
VYHOD = r'C:\sender\_ops\park_ingest_3b.jsonl'
PROVERIT = 20
POROG = 0.6          # ниже этой доли открывшихся поток не пишу

NOMER_EPB = re.compile(r'(?:заключени\w*\s+ЭПБ\s*)?№?\s*(\d{2}-[А-Я]{2,3}-\d{3,7}-\d{4})', re.U)
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
KLASS = {'ГПА': 5, 'компрессор': 4, 'нагнетатель': 4, 'ВРУ': 4, 'генератор азота': 4,
         'генератор кислорода': 4, 'воздуходувка': 3, 'МКС / передвижная': 3, 'осушитель': 2}
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
net = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                  urllib.request.ProxyHandler({}))


def klyuch(s):
    return re.sub(r'[\s\-]', '', s).upper().replace(',', '.')


def adres(nomer):
    return 'https://monitor-pb.ru/conclusion/' + urllib.parse.quote(nomer, safe='')


prov = {}
if os.path.exists(RAZOBRANY):
    try:
        for o in json.loads(io.open(RAZOBRANY, encoding='utf-8').read()):
            prov[klyuch(o.get('seriya') or '')] = o
    except Exception:  # noqa: BLE001
        pass

zapisi = collections.defaultdict(lambda: {'v': 0, 'p': collections.Counter(),
                                          'vid': collections.Counter(), 'nom': set(),
                                          'iz': set(), 'napis': set(), 'cit': '',
                                          'sem': collections.Counter()})
prichiny = collections.Counter()
bez_ssylki_po_baze = collections.Counter()
for baza, tabl in ISTOCHNIKI:
    if not os.path.exists(baza):
        continue
    try:
        cx = sqlite3.connect('file:%s?mode=ro' % baza.replace('\\', '/'), uri=True)
        kol = [r[1] for r in cx.execute('pragma table_info("%s")' % tabl)]
    except Exception:  # noqa: BLE001
        continue
    if not kol:
        cx.close()
        continue
    pinn = 'inn' if 'inn' in kol else ('company_inn' if 'company_inn' in kol else None)
    metka = '%s/%s' % (os.path.basename(baza), tabl)
    for r in cx.execute('select %s from "%s"' % (','.join('"%s"' % k for k in kol), tabl)):
        d = dict(zip(kol, r))
        tekst = ' '.join(str(v) for v in r if v is not None)
        if len(tekst) < 8:
            continue
        if URL.search(tekst):
            continue                      # эти уже ушли первым потоком
        bez_ssylki_po_baze[metka] += 1
        if POMETKA_NE_MASHINA.search(tekst):
            prichiny['разметка строки: машина лишь упомянута'] += 1
            continue
        inn = ''
        if pinn and str(d.get(pinn) or '').strip().isdigit():
            inn = str(d[pinn]).strip()
        else:
            m = INN_RYADOM.search(tekst)
            inn = m.group(1) if m else ''
        if not inn:
            prichiny['ИНН нет'] += 1
            continue
        nomera = set(NOMER_EPB.findall(tekst))
        if not nomera:
            prichiny['номера документа в строке тоже нет — вернуть нечем'] += 1
            continue
        for sem, rg in SEMEYSTVA:
            for m in rg.finditer(tekst):
                syr = m.group(1)
                do = tekst[max(0, m.start() - 60):m.start()]
                okno = tekst[max(0, m.start() - 130):m.end() + 130]
                if POZ.search(do):
                    prichiny['позиция / зав. №'] += 1
                    continue
                if CHUZH.search(okno):
                    prichiny['чужая машина в окне'] += 1
                    continue
                k = klyuch(syr)
                if prov.get(k) and not prov[k].get('nashe'):
                    prichiny['вердикт провайдера: не наша машина'] += 1
                    continue
                z = zapisi[(inn, k)]
                z['v'] += 1
                z['napis'].add(syr)
                z['sem'][sem] += 1
                z['iz'].add(metka)
                z['nom'] |= nomera
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

kandidaty = []
for (inn, k), z in zapisi.items():
    vid = (z['vid'].most_common(1) or [('', 0)])[0][0]
    if not vid:
        prichiny['вид машины текстом не доказан'] += 1
        continue
    kandidaty.append((inn, k, z, sorted(z['nom'])))

# --- ПРОВЕРКА ШАБЛОНА: открываем двадцать случайных
random.seed(20260809)
obrazcy = random.sample(kandidaty, min(PROVERIT, len(kandidaty))) if kandidaty else []
itogi_proverki = []
for inn, k, z, nomera in obrazcy:
    nom = nomera[0]
    u = adres(nom)
    try:
        rq = urllib.request.Request(u, headers={'User-Agent': UA, 'Accept-Language': 'ru'})
        with net.open(rq, timeout=60) as rs:
            kod = rs.getcode()
            body = rs.read(400000).decode('utf-8', 'replace')
        text = re.sub(r'<[^>]+>', ' ', body)
        text = re.sub(r'\s+', ' ', text)
        est_nomer = nom in text
        est_obozn = any(klyuch(n) in klyuch(text) for n in list(z['napis'])[:3])
        if est_nomer and est_obozn:
            verdikt = 'ДОКАЗЫВАЕТ: номер и обозначение на странице'
        elif est_nomer:
            verdikt = 'открылась, номер есть, обозначения машины нет'
        else:
            verdikt = 'открылась, но это не тот документ (номера нет)'
    except Exception as e:  # noqa: BLE001
        kod, verdikt = 0, 'не открылась: %s' % str(e)[:50]
    itogi_proverki.append((nom, kod, verdikt, inn, ' | '.join(sorted(z['napis'])[:2])))

horosho = sum(1 for _, _, v, _, _ in itogi_proverki if v.startswith('ДОКАЗЫВАЕТ'))
otkrylis = sum(1 for _, k2, v, _, _ in itogi_proverki if not v.startswith('не открылась'))
dolya = (horosho / float(len(itogi_proverki))) if itogi_proverki else 0.0

potok = []
if dolya >= POROG:
    for inn, k, z, nomera in kandidaty:
        vid = (z['vid'].most_common(1) or [('', 0)])[0][0]
        ss = [adres(n) for n in nomera]
        potok.append({
            'inn': inn, 'klyuch': k,
            'napisanie': ' | '.join(sorted(z['napis'])[:4]),
            'vid': vid,
            'princip': (z['p'].most_common(1) or [('не установлен', 0)])[0][0],
            'vetka': (z['sem'].most_common(1) or [('', 0)])[0][0],
            'klass_ceny': KLASS.get(vid, 2),
            'vstrech': z['v'],
            'istochniki': ' | '.join(ss),
            'istochnikov': len(ss),
            'ssylka_otkuda': 'собрана из номера заключения ЭПБ, шаблон проверен %d из %d'
                             % (horosho, len(itogi_proverki)),
            'nomera_dokumentov': ' | '.join(nomera),
            'dokazano_iz': ' | '.join(sorted(z['iz'])),
            'citata': z['cit'],
            'kto': '3-я сессия, park_ingest_3b (ссылка из номера)',
        })
    with io.open(VYHOD, 'w', encoding='utf-8') as f:
        for o in potok:
            f.write(json.dumps(o, ensure_ascii=False) + '\n')

vylozheno = 'поток не писала — шаблон не подтвердился'
if potok:
    try:
        o2 = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'),
                                                os.path.basename(VYHOD)),
                                     data=io.open(VYHOD, 'rb').read(), method='PUT',
                                     headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
        vylozheno = o2.open(req, timeout=300).read().decode('utf-8', 'replace')[:110]
    except Exception as e:  # noqa: BLE001
        vylozheno = 'не выложено: %s' % str(e)[:90]

print('\n\n########## ПРОВЕРКА ШАБЛОНА ГЛАЗАМИ (двадцать случайных)')
for nom, kod, v, inn, nap in itogi_proverki:
    print('  %-22s http %-4s %-14s %-22s %s' % (nom, kod, inn, nap[:22], v))
print('\n########## ЧИСЛА')
print('  строк без ссылки прочитано')
for k, v in bez_ssylki_po_baze.most_common():
    print('     %-34s %8d' % (k, v))
print('  кандидатов (ИНН+серия+номер)  %8d' % len(kandidaty))
print('  проверено ссылок              %8d' % len(itogi_proverki))
print('  из них доказывают             %8d' % horosho)
print('  просто открылись              %8d' % otkrylis)
print('  доля доказывающих             %8.2f  (порог %.2f)' % (dolya, POROG))
print('  записей в потоке              %8d' % len(potok))
print('  разных ИНН                    %8d' % len({o['inn'] for o in potok}))
print('  --- почему остальные не вернулись')
for k, v in prichiny.most_common(10):
    print('     %-52s %8d' % (k[:52], v))
print('  выложено: %s' % vylozheno)
print('ИТОГ ' + json.dumps({'кандидатов': len(kandidaty), 'доказывают из 20': horosho,
                            'записей': len(potok),
                            'ИНН': len({o['inn'] for o in potok})}, ensure_ascii=False))
