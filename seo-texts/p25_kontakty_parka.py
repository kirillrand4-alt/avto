# -*- coding: utf-8 -*-
"""Контакты ПО ПАРКУ: беру ИНН, у которых машина уже доказана, и собираю к ним людей.

Порядок именно такой и он не случаен. Владелец мерит результат одним числом — «сколько
ЛИЧНЫХ номеров ЛПР у предприятия с доказанным отношением к машине». Значит контакт без
доказанной машины не считается вовсе, и начинать надо с парка, а не с телефонной книги.

Вход — мой же поток `park_ingest_3.jsonl` (1 380 записей, 439 ИНН, у 800 записей две и
более ссылки). К этим ИНН подтягиваю всё, что лежит в боевых базах.

ЧЕТЫРЕ ПРАВИЛА, УЖЕ ОПЛАЧЕННЫЕ ОШИБКАМИ, ПРИМЕНЯЮ СРАЗУ:

1. РАЗДЕЛЯТЬ, А НЕ ОТСЕИВАТЬ. Приёмная, 8-800, общий, добавочный — всё сохраняется со
   своей пометкой. Ноль по личным номерам не значит «выбросить»: неличный номер это путь
   к человеку через коммутатор.
2. НОМЕР У НЕСКОЛЬКИХ ПРЕДПРИЯТИЙ — НЕ ЛИЧНЫЙ. Это правило поймало больше всех: мой
   собственный замер личных мобильных прошёл путь 818 -> 613 -> 249 именно из-за него, и
   поймала его соседняя сессия, а не я. Считаю номер по всем ИНН сразу и понижаю общие.
3. ДОКАЗАТЕЛЬСТВ СТОЛЬКО, СКОЛЬКО УНИКАЛЬНЫХ ССЫЛОК. Один человек, найденный пятью
   путями, — это один контакт с пятью ссылками, а не пять строк и не одна.
4. БЛИЗОСТЬ К ФАМИЛИИ НЕ ДОКАЗЫВАЕТ ПРИНАДЛЕЖНОСТЬ НОМЕРА. Поэтому связка «человек —
   номер» принимается только там, где она стоит в самой базе, а не собрана мной по
   расстоянию в тексте; собранное расстоянием помечается отдельно.

Колонки таблиц не угадываю — читаю `pragma table_info` и печатаю, какие поля выбрала.
Прошлый раз угадывание имени поля стоило отдельного захода.

Только чтение. Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import sqlite3
import urllib.request

VHOD = r'C:\sender\_ops\park_ingest_3.jsonl'
BAZY = [r'C:\sender\enrich.db', r'C:\seostat\drop\drop-storage\atlas_copco.db',
        r'C:\seostat\data\centrifugal.db']
VYHOD = r'C:\sender\_ops\PARK-KONTAKTY-3S.jsonl'

P_INN = re.compile(r'^(inn|company_inn|firma_inn|org_inn)$', re.I)
P_TEL = re.compile(r'phone|tel|mobil|номер', re.I)
P_POCHTA = re.compile(r'email|mail', re.I)
P_IMYA = re.compile(r'^(name|fio|full_name|person|person_name|contact_name)$', re.I)
P_DOLZH = re.compile(r'^(position|dolzhnost|role|post)$', re.I)
P_URL = re.compile(r'url|link|source|istochnik|ssylk', re.I)
URL = re.compile(r'https?://[^\s"\'<>|;,]+')
DOB = re.compile(r'доб\.?\s*\d{1,5}|ext\.?\s*\d{1,5}', re.I)
# ФИО ЧЕЛОВЕКА, а не два слова с большой буквы. Первый заход дал «Группы Черкизово» в
# графе имени и посчитал номер личным — потому что шаблон требовал лишь двух заглавных
# слов. Требую отчество (-ович/-евна/-ич/-ична) либо фамилию с инициалами.
FIO = re.compile(r'^[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё\-]{2,}\s+'
                 r'[А-ЯЁ][а-яё\-]{2,}(?:ович|евич|ьич|ич|овна|евна|ична|инична|ична)$|'
                 r'^[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.$|'
                 r'^[А-ЯЁ]\.\s?[А-ЯЁ]\.\s?[А-ЯЁ][а-яё\-]{2,}$')
# слова, после которых «имя» это на самом деле кусок названия организации
NE_CHELOVEK = re.compile(r'групп|филиал|завод|комбинат|общест|компан|холдинг|управлен|'
                         r'предприят|фабрик|станц|отдел|служб|цех|склад|офис|дирекц', re.I)
MUSOR_DOLZH = re.compile(r'^(есть только|общий|нет|—|-|\?|не |н/д)', re.I)


def desyat(t):
    c = re.sub(r'\D', '', str(t or ''))
    if len(c) == 11 and c[0] in '78':
        c = c[1:]
    return c if len(c) == 10 else ''


def vid_nomera(syroy, des):
    if not des:
        return 'не номер'
    if des.startswith('800'):
        return '8-800 (линия предприятия)'
    if DOB.search(str(syroy or '')):
        return 'общий с добавочным'
    if des[0] == '9':
        return 'мобильный'
    return 'городской'


inn_parka, po_inn_mashina = set(), {}
if os.path.exists(VHOD):
    for s in io.open(VHOD, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        inn_parka.add(o['inn'])
        po_inn_mashina.setdefault(o['inn'], []).append(o['vid'])

# сбор: ключ = (ИНН, 10 цифр номера) либо (ИНН, почта)
tel = collections.defaultdict(lambda: {'syr': set(), 'imya': set(), 'dolzh': set(),
                                       'url': set(), 'iz': set(), 'vid': collections.Counter()})
pochta = collections.defaultdict(lambda: {'imya': set(), 'url': set(), 'iz': set()})
nomer_u_inn = collections.defaultdict(set)
vybor_poley, prochitano = [], collections.Counter()
otbrakovka, primery_otbrakovki = collections.Counter(), []
DVA_SLOVA = re.compile(r'^[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё\-]{2,}')

for baza in BAZY:
    if not os.path.exists(baza):
        continue
    try:
        cx = sqlite3.connect('file:%s?mode=ro' % baza.replace('\\', '/'), uri=True)
        tabl = [r[0] for r in cx.execute(
            "select name from sqlite_master where type='table'")]
    except Exception:  # noqa: BLE001
        continue
    for t in tabl:
        try:
            kol = [r[1] for r in cx.execute('pragma table_info("%s")' % t)]
        except Exception:  # noqa: BLE001
            continue
        k_inn = [k for k in kol if P_INN.match(k)]
        k_tel = [k for k in kol if P_TEL.search(k)]
        k_pch = [k for k in kol if P_POCHTA.search(k)]
        if not k_inn or not (k_tel or k_pch):
            continue
        k_imya = [k for k in kol if P_IMYA.match(k)] or [k for k in kol if k.lower() in ('fio', 'person')]
        k_dol = [k for k in kol if P_DOLZH.search(k)]
        k_url = [k for k in kol if P_URL.search(k)]
        metka = '%s/%s' % (os.path.basename(baza), t)
        vybor_poley.append('%-34s инн=%s тел=%s почта=%s имя=%s должн=%s ссылка=%s'
                           % (metka, ','.join(k_inn[:1]), ','.join(k_tel[:2]),
                              ','.join(k_pch[:1]), ','.join(k_imya[:1]),
                              ','.join(k_dol[:1]), ','.join(k_url[:1])))
        try:
            kur = cx.execute('select %s from "%s"' % (','.join('"%s"' % k for k in kol), t))
        except Exception:  # noqa: BLE001
            continue
        for r in kur:
            d = dict(zip(kol, r))
            inn = str(d.get(k_inn[0]) or '').strip()
            if not inn:
                continue
            prochitano[metka] += 1
            stroka = ' '.join(str(v) for v in r if v is not None)
            ssylki = set(URL.findall(stroka))
            for ku in k_url:
                v = str(d.get(ku) or '').strip()
                if v.startswith('http'):
                    ssylki.add(v)
            imya = ''
            for ki in k_imya:
                v = re.sub(r'\s+', ' ', str(d.get(ki) or '')).strip()
                if FIO.match(v) and not NE_CHELOVEK.search(v):
                    imya = v
                    break
                if DVA_SLOVA.match(v):
                    otbrakovka['два слова с большой буквы, но не ФИО человека'] += 1
                    if len(primery_otbrakovki) < 8:
                        primery_otbrakovki.append(v[:50])
            dolzh = ''
            for kd in k_dol:
                v = re.sub(r'\s+', ' ', str(d.get(kd) or '')).strip()
                if 2 < len(v) < 90 and not MUSOR_DOLZH.match(v):
                    dolzh = v
                    break
            for kt in k_tel:
                syroy = str(d.get(kt) or '').strip()
                des = desyat(syroy)
                if not des:
                    continue
                nomer_u_inn[des].add(inn)
                if inn not in inn_parka:
                    continue
                z = tel[(inn, des)]
                z['syr'].add(syroy[:40])
                z['url'] |= ssylki
                z['iz'].add(metka)
                z['vid'][vid_nomera(syroy, des)] += 1
                if imya:
                    z['imya'].add(imya)
                if dolzh:
                    z['dolzh'].add(dolzh)
            for kp in k_pch:
                ad = str(d.get(kp) or '').strip().lower()
                if '@' not in ad or ' ' in ad or inn not in inn_parka:
                    continue
                z = pochta[(inn, ad)]
                z['url'] |= ssylki
                z['iz'].add(metka)
                if imya:
                    z['imya'].add(imya)
    cx.close()

potok = []
for (inn, des), z in tel.items():
    obshchih = len(nomer_u_inn.get(des, ()))
    vid = (z['vid'].most_common(1) or [('не номер', 0)])[0][0]
    if obshchih > 1:
        vid_itog = 'номер у %d предприятий — не личный' % obshchih
    elif vid == 'мобильный' and z['imya']:
        vid_itog = 'ЛИЧНЫЙ МОБИЛЬНЫЙ'
    elif vid == 'мобильный':
        vid_itog = 'мобильный без имени'
    else:
        vid_itog = vid
    ss = sorted(z['url'])
    potok.append({
        'inn': inn, 'nomer': des, 'napisanie': ' | '.join(sorted(z['syr'])[:2]),
        'vid_nomera': vid_itog,
        'imya': ' | '.join(sorted(z['imya'])[:2]),
        'dolzhnost': ' | '.join(sorted(z['dolzh'])[:2]),
        'mashina': ' | '.join(sorted(set(po_inn_mashina.get(inn, [])))[:3]),
        'istochniki': ' | '.join(ss), 'istochnikov': len(ss),
        'dokazano_iz': ' | '.join(sorted(z['iz'])),
        'u_skolkih_predpriyatiy': obshchih,
        'kto': '3-я сессия, контакты по парку',
    })
for (inn, ad), z in pochta.items():
    ss = sorted(z['url'])
    potok.append({
        'inn': inn, 'pochta': ad, 'vid_nomera': 'почта',
        'imya': ' | '.join(sorted(z['imya'])[:2]),
        'mashina': ' | '.join(sorted(set(po_inn_mashina.get(inn, [])))[:3]),
        'istochniki': ' | '.join(ss), 'istochnikov': len(ss),
        'dokazano_iz': ' | '.join(sorted(z['iz'])),
        'kto': '3-я сессия, контакты по парку',
    })
potok.sort(key=lambda o: (o['vid_nomera'] != 'ЛИЧНЫЙ МОБИЛЬНЫЙ', -o['istochnikov']))
with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for o in potok:
        f.write(json.dumps(o, ensure_ascii=False) + '\n')

vylozheno = 'не выкладывала'
try:
    o2 = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'),
                                            os.path.basename(VYHOD)),
                                 data=io.open(VYHOD, 'rb').read(), method='PUT',
                                 headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    vylozheno = o2.open(req, timeout=300).read().decode('utf-8', 'replace')[:110]
except Exception as e:  # noqa: BLE001
    vylozheno = 'не выложено: %s' % str(e)[:90]

vidy = collections.Counter(o['vid_nomera'] for o in potok)
lichnye = [o for o in potok if o['vid_nomera'] == 'ЛИЧНЫЙ МОБИЛЬНЫЙ']
bez_ssylki = sum(1 for o in potok if o['istochnikov'] == 0)
print('\n\n########## КАКИЕ ПОЛЯ ВЫБРАНЫ')
for v in vybor_poley[:14]:
    print('  ' + v)
print('\n########## ПРИМЕРЫ ЛИЧНЫХ')
for o in lichnye[:6]:
    print('  %-12s %-11s %-28s %-26s ссылок %d' % (o['inn'], o['nomer'], o['imya'][:28],
                                                   (o['dolzhnost'] or '—')[:26], o['istochnikov']))
print('\n########## ЧИСЛА')
print('  ИНН парка на входе             %6d' % len(inn_parka))
print('  строк контактов собрано        %6d' % len(potok))
print('  ИНН, у которых есть контакт    %6d' % len({o['inn'] for o in potok}))
print('  ЛИЧНЫХ МОБИЛЬНЫХ               %6d  (на %d предприятиях)'
      % (len(lichnye), len({o['inn'] for o in lichnye})))
print('  из них со ссылкой              %6d' % sum(1 for o in lichnye if o['istochnikov']))
print('  строк без единой ссылки        %6d' % bez_ssylki)
print('  --- по виду')
for k, v in vidy.most_common(10):
    print('     %-46s %6d' % (k[:46], v))
print('  --- прочитано строк по таблицам')
for k, v in prochitano.most_common(8):
    print('     %-46s %8d' % (k, v))
print('  файл: %s' % VYHOD)
print('  выложено: %s' % vylozheno)
print('ИТОГ ' + json.dumps({'строк': len(potok), 'ИНН с контактом': len({o['inn'] for o in potok}),
                            'личных мобильных': len(lichnye),
                            'предприятий с личным': len({o['inn'] for o in lichnye})},
                           ensure_ascii=False))
