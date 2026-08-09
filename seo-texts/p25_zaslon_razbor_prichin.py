# -*- coding: utf-8 -*-
"""РАЗБОР заслона «не владелец» ПО ПРИЧИНАМ: какая причина настоящая, а какая ложная.

`p25_zaslon_ne_vladelec.py` пометил 1 320 ИНН одним числом, а поле `is_competitor` знает
из них 113. Число крупное — значит повод проверить прибор, а не радоваться. Причины у
заслона разной силы, и сваленные в одну кучу они неразличимы:

    сильная   «официальный дистрибьютор», «сервисный центр» в ОПИСАНИИ деятельности
    слабая    ОКВЭД 46.x/47.x — у производственного завода торговый код бывает ОСНОВНЫМ

Что здесь считается отдельно и почему:

1. Каждая причина — своим множеством РАЗНЫХ ИНН (не событий). В исходном приборе счётчик
   `sch[p] += 1` считал СТРОКИ, а `podozr` — ИНН; если у компании две строки, причина
   посчитана дважды, а ИНН один. Здесь обе величины рядом.

2. `продавец/сервис` разложен ПО СЛОВУ, которым сработал, и ПО МЕСТУ (описание или только
   название). Слова в этой пачке неравны: «дистрибьютор» — приговор, а `запчаст` и
   `комплектующ` ловят и «ПРОИЗВОДСТВО запчастей», то есть завод.

3. ОКВЭД. Поле хранит СПИСОК кодов через «|» (у Газпрома первый 46.71.4 — опт, а дальше
   06.10.3 добыча газа и 35.21). Исходный `OKVED_NE_VLADELEC.match(okv)` читает ТОЛЬКО
   ПЕРВЫЙ код. Поэтому считаю раздельно: первый код торговый — и есть ли в том же поле
   производственный код (05-09 добыча, 10-33 обработка, 35-39 энергия/вода). Второе и есть
   проверка гипотезы «у завода торговый ОКВЭД основной».

4. «Только слабая причина» — ИНН, у которого сработал лишь ОКВЭД и ни одной текстовой
   сильной. Это кандидаты на возврат в базу.

Вывод у раннера сохраняется ХВОСТОМ, и хвост короткий: полный блок ЧИСЕЛ в первом прогоне
съел собственную шапку. Поэтому раздел выбирается аргументом, примеры печатаются первыми,
а ЧИСЛА идут последними: в `chisla` — полностью, в разделах с примерами — кратким сводом,
чтобы примеры уместились в хвост.

    примеры по причине     konk prod podr nii imya okved
    примеры по разбору     slab zavod zavodimya zavodkod gipoteza prodzavod
    проверка прибора       syr        (чем на самом деле заполнены поля)
    числа                  chisla slova

Только чтение, mode=ro.
"""
import collections
import json
import re
import sqlite3
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:  # noqa: BLE001
    pass

CHAST = (sys.argv[1] if len(sys.argv) > 1 else 'chisla').strip().lower()

# --- те же слова, что в заслоне, но каждое названо: иначе не видно, чем сработало
PRODAVEC_SLOVA = [
    ('дистрибьютор', r'дистрибьютор'),
    ('дилер', r'дилер'),
    ('торговый дом', r'торгов\w+\s+дом'),
    ('поставка компр/оборуд', r'поставк\w+\s+(?:компрессор|оборудован)'),
    ('официальный представитель', r'официальн\w+\s+представител'),
    ('сервисный центр', r'сервисн\w+\s+центр'),
    ('сервисное обслуживание', r'сервисн\w+\s+обслуживан'),
    ('продажа компр/оборуд', r'продаж\w+\s+(?:компрессор|оборудован)'),
    ('аренда компр/оборуд', r'аренда\s+(?:компрессор|оборудован)'),
    ('ремонт компрессорн', r'ремонт\s+компрессорн'),
    ('ЗАПЧАСТ', r'запчаст'),
    ('КОМПЛЕКТУЮЩ', r'комплектующ'),
]
PODRYADCHIK_SLOVA = [
    ('строительство магистр/газопр/компр', r'строительств\w+\s+(?:магистральн|газопровод|компрессорн)'),
    ('монтаж оборуд/компрессорн', r'монтаж\w*\s+(?:оборудован|компрессорн)'),
    ('пусконаладочные', r'пусконаладочн'),
    ('проектирование компр/газопр', r'проектирован\w+\s+(?:компрессорн|газопровод)'),
]
NII_SLOVA = [
    ('НИИ', r'\bНИИ\b'),
    ('научно-исследовательск', r'научно-исследовательск'),
    ('конструкторское бюро', r'конструкторск\w+\s+бюро'),
    ('НИОКР', r'\bНИОКР\b'),
    ('ИНСТИТУТ', r'институт\b'),
]
SOBRAT = lambda pary: re.compile('|'.join(p for _, p in pary), re.I)  # noqa: E731
PRODAVEC = SOBRAT(PRODAVEC_SLOVA)
PODRYADCHIK = SOBRAT(PODRYADCHIK_SLOVA)
NII = SOBRAT(NII_SLOVA)
V_IMENI = re.compile(r'компрессор|\bМКС\b|пневмат|азот|кислород', re.I)
OKVED_NE_VLADELEC = re.compile(r'^(46|47|77|33|71|72|70|82|62|63)\.', re.I)

# Производственные разделы ОКВЭД: добыча 05-09, обработка 10-32, энергия/вода/отходы 35-39.
# Раздел 33 «Ремонт и монтаж машин и оборудования» СЮДА НЕ ВХОДИТ, хотя формально стоит
# внутри обрабатывающих: это ровно то занятие, которое заслон и ловит. Сначала я включила
# его в диапазон 10-33 — и получила противоречие в собственном своде: «есть производственный
# код» 122 плюс «только торговля» 42 давали 164 при 132 проверяемых. Лишние 32 — это
# компании с первым кодом 33.x, которым «производство» приписал мой же диапазон.
PROIZV_RAZDEL = set('%02d' % i for i in list(range(5, 10)) + list(range(10, 33))
                    + list(range(35, 40)))
# `\bПО\s` отсюда убран: с re.I он ловит предлог «по» в любом названии, а не
# «производственное объединение», и мера «заводское имя» стала бы решетом.
ZAVOD_V_IMENI = re.compile(
    r'\bзавод|комбинат|фабрик|\bГОК\b|\bНПЗ\b|\bТЭЦ\b|\bГРЭС\b|\bАЭС\b|шахт|рудник|'
    r'металлург|цемент|карьер|производствен|машиностро|приборостро|\bМЗ\b', re.I)
ZAVOD_V_DEYAT = re.compile(r'производств|добыч|переработк|обогащен|выплавк|литейн|'
                           r'\bцех\b|изготовлен', re.I)

PRICHINY = [
    ('konk', 'поле is_competitor'),
    ('prod', 'продавец/сервис'),
    ('podr', 'подрядчик'),
    ('nii', 'НИИ/КБ'),
    ('imya', 'машина в НАЗВАНИИ, а не в деятельности'),
    ('okved', 'ОКВЭД торговли/услуг (ПЕРВЫЙ код)'),
]
SILNYE_TEKST = ('prod', 'podr', 'nii')          # то, что владелец назвал сильным
SILNYE_VSE = ('konk', 'prod', 'podr', 'nii', 'imya')

# Половина слов пачки «продавец/сервис» НЕ НАЗЫВАЕТ ПРЕДМЕТ: «дистрибьютор» без
# «компрессоров» ловит дистрибьютора семян и продуктов питания, а «торговый дом» — сбытовую
# контору завода. Слова с названным предметом («поставка компрессоров») этим не болеют.
# Считаю разделение, иначе сила причины меряется вперемешку.
PROD_BEZ_PREDMETA = {'дистрибьютор', 'дилер', 'торговый дом', 'официальный представитель',
                     'сервисный центр', 'сервисное обслуживание', 'ЗАПЧАСТ', 'КОМПЛЕКТУЮЩ'}


KOD_RE = re.compile(r'(?<![\d.])(\d{2}(?:\.\d{1,2}){0,3})(?![\d])')


def kody(okv):
    """Поле ОКВЭД хранит код ВМЕСТЕ С РАСШИФРОВКОЙ («77.32 Аренда и лизинг…»), а кодов в
    поле бывает несколько. Резать по запятой нельзя: запятая стоит внутри расшифровки
    («Торговля оптовая топливом, рудами») и даёт мусорные куски. Тяну сами коды."""
    return KOD_RE.findall(str(okv or ''))


# «ООО»/«АКЦИОНЕРНОЕ ОБЩЕСТВО» съедали всю ширину строки примера, и глазами было видно
# только организационную форму. Режу форму и кавычки, чтобы читалось само имя.
FORMA = [
    (re.compile(r'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ', re.I), 'ООО'),
    (re.compile(r'ПУБЛИЧНОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО', re.I), 'ПАО'),
    (re.compile(r'(?:НЕПУБЛИЧНОЕ\s+)?АКЦИОНЕРНОЕ ОБЩЕСТВО', re.I), 'АО'),
    (re.compile(r'ЗАКРЫТОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО', re.I), 'ЗАО'),
    (re.compile(r'ОТКРЫТОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО', re.I), 'ОАО'),
    (re.compile(r'ФЕДЕРАЛЬНОЕ ГОСУДАРСТВЕННОЕ (?:УНИТАРНОЕ|БЮДЖЕТНОЕ)\s*'
                r'(?:ПРЕДПРИЯТИЕ|УЧРЕЖДЕНИЕ)', re.I), 'ФГУП/ФГБУ'),
    (re.compile(r'НАУЧНО-ИССЛЕДОВАТЕЛЬСК\w+', re.I), 'НАУЧН-ИССЛЕД'),
]


def korotko(nazv):
    s = str(nazv or '')
    for rx, zam in FORMA:
        s = rx.sub(zam, s)
    return re.sub(r'\s+', ' ', s.replace('"', '').replace('«', '').replace('»', '')).strip()


def razdel(kod):
    m = re.match(r'\s*(\d{1,2})', str(kod or ''))
    return ('%02d' % int(m.group(1))) if m else ''


cx = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True)
KOL = [r[1] for r in cx.execute('pragma table_info(companies)')]
sel = ','.join('"%s"' % k for k in KOL)
POLE_OKVED_ALL = 'okved_all' if 'okved_all' in KOL else None

inn_po_prichine = collections.defaultdict(set)
strok_po_prichine = collections.Counter()
primery = collections.defaultdict(list)
slovo_prod = collections.Counter()
slovo_podr = collections.Counter()
slovo_nii = collections.Counter()
mesto_prod = collections.Counter()
mesto_nii = collections.Counter()
podozr, vse_inn, strok = set(), set(), 0
zapis = {}     # inn -> сырьё для примеров и второго прохода


def stroka_primera(d):
    ks = kody(d['okv']) + kody(d['okv_all'])
    return ('  · %s | ОКВЭД %s | %s\n      деят: %s'
            % (d['inn'], (', '.join(ks) or '(пусто)')[:44],
               (korotko(d['nazv']) or '(без названия)')[:56],
               (d['act'] or '(ОПИСАНИЯ НЕТ)')[:135]))


for r in cx.execute('select %s from companies' % sel):
    d = dict(zip(KOL, r))
    inn = str(d.get('inn') or '').strip()
    if not inn:
        continue
    strok += 1
    vse_inn.add(inn)
    nazv = (str(d.get('name') or '') + ' ' + str(d.get('short_name') or '')).strip()
    act = str(d.get('activity') or '')
    okv = str(d.get('okved') or '')
    okv_all = str(d.get(POLE_OKVED_ALL) or '') if POLE_OKVED_ALL else ''
    pr = set()

    if str(d.get('is_competitor') or '0') not in ('0', '', 'None'):
        pr.add('konk')
    prod_slova = set()
    if PRODAVEC.search(act) or PRODAVEC.search(nazv):
        pr.add('prod')
        for imya_sl, pat in PRODAVEC_SLOVA:
            v_act = bool(re.search(pat, act, re.I))
            v_nazv = bool(re.search(pat, nazv, re.I))
            if v_act or v_nazv:
                slovo_prod[imya_sl] += 1
                prod_slova.add(imya_sl)
        mesto_prod['в описании деятельности' if PRODAVEC.search(act)
                   else 'ТОЛЬКО в названии'] += 1
    if PODRYADCHIK.search(act):
        pr.add('podr')
        for imya_sl, pat in PODRYADCHIK_SLOVA:
            if re.search(pat, act, re.I):
                slovo_podr[imya_sl] += 1
    if NII.search(act) or NII.search(nazv):
        pr.add('nii')
        for imya_sl, pat in NII_SLOVA:
            if re.search(pat, act, re.I) or re.search(pat, nazv, re.I):
                slovo_nii[imya_sl] += 1
        mesto_nii['в описании деятельности' if NII.search(act)
                  else 'ТОЛЬКО в названии'] += 1
    if V_IMENI.search(nazv) and not V_IMENI.search(act):
        pr.add('imya')
    if OKVED_NE_VLADELEC.match(okv):
        pr.add('okved')

    if not pr:
        continue
    podozr.add(inn)
    zap = {'inn': inn, 'nazv': nazv, 'act': act, 'okv': okv, 'okv_all': okv_all,
           'pr': pr, 'prod_slova': prod_slova}
    if inn not in zapis:
        zapis[inn] = zap
    else:
        zapis[inn]['pr'] = zapis[inn]['pr'] | pr
        zapis[inn]['prod_slova'] = zapis[inn]['prod_slova'] | prod_slova
    for k in pr:
        strok_po_prichine[k] += 1
        inn_po_prichine[k].add(inn)
        if len(primery[k]) < 10 and inn not in [x[0] for x in primery[k]]:
            primery[k].append((inn, zap))
cx.close()

# --- второй проход по накопленным записям: слабая причина и её честность
tolko_slabaya = set()          # только ОКВЭД, ни одной ТЕКСТОВОЙ сильной
tolko_slabaya_strogo = set()   # только ОКВЭД, вообще никакой другой причины
slab_s_proizv = []             # есть производственный код СРЕДИ ИЗВЕСТНЫХ
slab_zavod_imya = []           # заводское слово в названии
slab_zavod_deyat = []          # производство в описании
raspred_slab = collections.Counter()
raspred_slab_2 = collections.Counter()
# Честные знаменатели. Второй код виден ТОЛЬКО у тех, у кого заполнен okved_all: сам
# `okved` хранит ровно один код с расшифровкой. Без этого деления «все коды торговые»
# означало бы «другого кода мы не знаем», а читалось бы как «другого кода нет».
slab_bez_spiska = 0            # okved_all пуст — судить не по чему
slab_so_spiskom = 0
slab_spisok_tolko_torg = 0
torg4647 = 0                   # первый код 46.x/47.x — та самая гипотеза владельца
torg4647_spisok = 0
torg4647_proizv = 0
gipoteza = []                  # поимённо: торговый код основной, а компания производит
# «заводское слово» — не одно слово. Развожу твёрдое («ЗАВОД», «комбинат») и мягкое
# («научно-производственное»), иначе одно число выдаёт НПО за заводы.
IMYA_TVERDO = re.compile(r'\bзавод|комбинат|фабрик|\bГОК\b|\bНПЗ\b|\bТЭЦ\b|\bГРЭС\b|'
                         r'\bАЭС\b|шахт|рудник|металлург|цемент|карьер', re.I)
IMYA_MYAGKO = re.compile(r'производствен|машиностро|приборостро', re.I)
imya_tverdo = imya_myagko = 0
for inn, z in zapis.items():
    if 'okved' not in z['pr']:
        continue
    if z['pr'] & set(SILNYE_TEKST):
        continue
    tolko_slabaya.add(inn)
    if not (z['pr'] & set(SILNYE_VSE)):
        tolko_slabaya_strogo.add(inn)
    k1 = kody(z['okv'])
    k2 = kody(z['okv_all'])
    ks = k1 + k2
    pervyy = razdel(k1[0]) if k1 else '(пусто)'
    raspred_slab[pervyy] += 1
    est_proizv = [k for k in ks if razdel(k) in PROIZV_RAZDEL]
    for k in ks[1:]:
        raspred_slab_2[razdel(k)] += 1
    if k2:
        slab_so_spiskom += 1
        if not est_proizv:
            slab_spisok_tolko_torg += 1
    else:
        slab_bez_spiska += 1
    if est_proizv:
        slab_s_proizv.append((inn, z, est_proizv))
    if pervyy in ('46', '47'):
        torg4647 += 1
        if k2:
            torg4647_spisok += 1
            if est_proizv:
                torg4647_proizv += 1
                gipoteza.append((inn, z, est_proizv))
    if ZAVOD_V_IMENI.search(z['nazv']):
        slab_zavod_imya.append((inn, z, est_proizv))
        if IMYA_TVERDO.search(z['nazv']):
            imya_tverdo += 1
        elif IMYA_MYAGKO.search(z['nazv']):
            imya_myagko += 1
    if ZAVOD_V_DEYAT.search(z['act']):
        slab_zavod_deyat.append((inn, z, est_proizv))

# «продавец/сервис»: назван ли ПРЕДМЕТ торговли. Если нет — проверяю по ОКВЭД, не завод ли
# это: производственный код при слове «дистрибьютор» означает, что торгует он СВОИМ, а
# машина у него стоит.
prod_bez_predmeta, prod_bez_predmeta_zavod = [], []
for inn in inn_po_prichine['prod']:
    z = zapis[inn]
    if z['prod_slova'] and z['prod_slova'] <= PROD_BEZ_PREDMETA:
        prod_bez_predmeta.append(inn)
        if razdel((kody(z['okv']) or [''])[0]) in PROIZV_RAZDEL:
            prod_bez_predmeta_zavod.append((inn, z))

# Описание деятельности пустое у большинства — тогда ТЕКСТОВЫЕ причины по нему просто не
# могли сработать, а причина «машина в названии, а НЕ в деятельности» вырождается:
# «не в деятельности» истинно потому, что деятельности НЕТ ВОВСЕ.
ZAGLUSHKA = re.compile(r'не определено|контент сайта не получен|нет данных|'
                       r'не удалось|информация отсутств', re.I)
zaglushka_act = sum(1 for z in zapis.values()
                    if str(z['act']).strip() and ZAGLUSHKA.search(str(z['act'])))
pusto_act_vsego = sum(1 for z in zapis.values() if not str(z['act']).strip())
pusto_act_po_prichine = {k: sum(1 for i in inn_po_prichine[k]
                                if not str(zapis[i]['act']).strip())
                         for k, _ in PRICHINY}

# ================= ПРИМЕРЫ (идут ПЕРЕД числами — хвост вывода сохраняет числа)
IMENA = dict(PRICHINY)
if CHAST in IMENA:
    print('########## ПРИМЕРЫ, причина: %s  (всего ИНН %d)'
          % (IMENA[CHAST], len(inn_po_prichine[CHAST])))
    for inn, z in primery[CHAST]:
        print(stroka_primera(z))
        print('      прочие причины у этого ИНН: %s'
              % (', '.join(sorted(IMENA[p] for p in z['pr'] if p != CHAST)) or 'нет'))
elif CHAST == 'slab':
    print('########## ПРИМЕРЫ: ТОЛЬКО слабая причина (ОКВЭД), ни одной текстовой сильной')
    for inn in sorted(tolko_slabaya)[:10]:
        print(stroka_primera(zapis[inn]))
elif CHAST == 'gipoteza':
    print('########## ГИПОТЕЗА ВЛАДЕЛЬЦА ПОИМЁННО: основной ОКВЭД торговый 46.x/47.x,')
    print('##########   а компания производит (%d ИНН из %d проверяемых)'
          % (len(gipoteza), torg4647_spisok))
    for inn, z, est in gipoteza[:10]:
        print(stroka_primera(z))
        print('      производственные коды в том же поле: %s' % (', '.join(est))[:100])
elif CHAST == 'prodzavod':
    print('########## ПРИМЕРЫ: «продавец/сервис» сработал БЕЗ НАЗВАННОГО ПРЕДМЕТА,')
    print('##########           а ОКВЭД у компании ПРОИЗВОДСТВЕННЫЙ (%d ИНН)'
          % len(prod_bez_predmeta_zavod))
    for inn, z in prod_bez_predmeta_zavod[:10]:
        print(stroka_primera(z))
        print('      сработало по словам: %s' % ', '.join(sorted(z['prod_slova'])))
elif CHAST == 'syr':
    # Проверка прибора: вся мера «производственный код рядом» стоит на том, что в поле
    # ОКВЭД лежит НЕ ОДИН код. Если кодов там всегда по одному — мера пустая, и это надо
    # знать до выводов, а не после.
    print('########## СЫРЬЁ: чем на самом деле заполнено поле ОКВЭД')
    print('  колонки companies: %s' % ', '.join(KOL)[:700])
    mnogo = [(i, z) for i, z in zapis.items() if len(kody(z['okv'])) > 1]
    print('  подозрительных ИНН с ДВУМЯ И БОЛЕЕ кодами в поле okved: %d из %d'
          % (len(mnogo), len(zapis)))
    for i, z in mnogo[:6]:
        print('  · %s okved = %s' % (i, str(z['okv'])[:190]))
    odin = [(i, z) for i, z in zapis.items() if len(kody(z['okv'])) == 1]
    print('  --- с ОДНИМ кодом (%d), как выглядит поле' % len(odin))
    for i, z in odin[:4]:
        print('  · %s okved = %s' % (i, str(z['okv'])[:150]))
    if POLE_OKVED_ALL:
        s_all = [(i, z) for i, z in zapis.items() if str(z['okv_all']).strip()]
        print('  --- колонка %s заполнена у %d подозрительных' % (POLE_OKVED_ALL, len(s_all)))
        for i, z in s_all[:4]:
            print('  · %s %s = %s' % (i, POLE_OKVED_ALL, str(z['okv_all'])[:170]))
    else:
        print('  --- колонки okved_all в companies НЕТ')
    pusto_act = sum(1 for z in zapis.values() if not str(z['act']).strip())
    print('  у подозрительных ПУСТОЕ описание деятельности: %d из %d'
          % (pusto_act, len(zapis)))
elif CHAST in ('zavod', 'zavodimya', 'zavodkod'):
    # Три половины разнесены по прогонам: в один хвост они не влезают, и в первом заходе
    # раздел А был съеден целиком — то есть примеров, ради которых прогон и делался, я не
    # увидела бы вовсе.
    if CHAST == 'zavodimya':
        print('########## ПРИМЕРЫ: слабая причина, а в НАЗВАНИИ заводское слово (%d ИНН)'
              % len(slab_zavod_imya))
        vyborka = slab_zavod_imya
    elif CHAST == 'zavodkod':
        print('########## ПРИМЕРЫ: слабая причина, а в списке ОКВЭД есть ПРОИЗВОДСТВО'
              ' (%d ИНН)' % len(slab_s_proizv))
        vyborka = slab_s_proizv
    else:
        print('########## ПРИМЕРЫ: слабая причина, а в ОПИСАНИИ производство (%d ИНН)'
              % len(slab_zavod_deyat))
        vyborka = slab_zavod_deyat
    for inn, z, est in vyborka[:10]:
        print(stroka_primera(z))
        print('      производственные коды в том же поле: %s'
              % ((', '.join(est))[:100] or 'НЕТ'))

# ================= ЧИСЛА (всегда в самом конце)
if CHAST == 'slova':
    # Хвост раннера держит ~3 500 знаков, весь свод в него не влезает: в первом полном
    # прогоне он съел собственную шапку. Поэтому числа разнесены на два прогона —
    # `chisla` (сколько и почему) и `slova` (чем именно сработало).
    print('########## ЧЕМ ИМЕННО СРАБОТАЛО (строк)')
    print('  --- продавец/сервис')
    for s, n in slovo_prod.most_common():
        print('      %-34s %6d' % (s, n))
    for s, n in mesto_prod.most_common():
        print('      место: %-27s %6d' % (s, n))
    print('      ИНН, где сработали ТОЛЬКО слова без предмета  %6d из %d'
          % (len(prod_bez_predmeta), len(inn_po_prichine['prod'])))
    print('      из них ПЕРВЫЙ ОКВЭД производственный (завод!) %6d'
          % len(prod_bez_predmeta_zavod))
    print('  --- подрядчик')
    for s, n in slovo_podr.most_common():
        print('      %-34s %6d' % (s, n))
    print('  --- НИИ/КБ')
    for s, n in slovo_nii.most_common():
        print('      %-34s %6d' % (s, n))
    for s, n in mesto_nii.most_common():
        print('      место: %-27s %6d' % (s, n))
    print('\n  --- «только слабая»: ПЕРВЫЙ код ОКВЭД по двум цифрам')
    for s, n in raspred_slab.most_common(12):
        print('      %-6s %6d' % (s or '(пусто)', n))
    print('  --- «только слабая»: ОСТАЛЬНЫЕ коды того же поля (okved_all), по двум цифрам')
    for s, n in raspred_slab_2.most_common(14):
        print('      %-6s %6d%s' % (s or '(пусто)', n,
                                    '   <- ПРОИЗВОДСТВО' if s in PROIZV_RAZDEL else ''))
    print('ИТОГ ' + json.dumps({'раздел': CHAST, 'продавец/сервис ИНН':
                                len(inn_po_prichine['prod'])}, ensure_ascii=False))
    raise SystemExit(0)

if CHAST != 'chisla':
    # хвост раннера короткий: полный свод затёр бы примеры, ради которых прогон и сделан
    print('\n  ##### ЧИСЛА кратко (полностью — прогон `chisla`)')
    print('  подозрительных ИНН %d | поле is_competitor знает %d'
          % (len(podozr), len(inn_po_prichine['konk'])))
    print('  ' + ' | '.join('%s %d' % (nm.split()[0], len(inn_po_prichine[k]))
                            for k, nm in PRICHINY))
    print('  только слабая ОКВЭД %d, из них с производственным кодом рядом %d, '
          'заводское имя %d, производство в описании %d'
          % (len(tolko_slabaya), len(slab_s_proizv), len(slab_zavod_imya),
             len(slab_zavod_deyat)))
    print('ИТОГ ' + json.dumps({'раздел': CHAST, 'подозрительных ИНН': len(podozr)},
                               ensure_ascii=False))
    raise SystemExit(0)

print('\n\n########## ЧИСЛА, посчитано на живой C:\\sender\\enrich.db')
print('  колонки companies, которые читаю: inn,name,short_name,activity,okved,'
      'is_competitor%s' % (',' + POLE_OKVED_ALL if POLE_OKVED_ALL else ' (okved_all НЕТ)'))
print('  строк с ИНН %d | РАЗНЫХ ИНН %d | под подозрением РАЗНЫХ ИНН %d'
      % (strok, len(vse_inn), len(podozr)))
print('\n  --- по причинам, РАЗНЫХ ИНН (причины пересекаются)')
for k, nm in PRICHINY:
    print('  %-42s ИНН %6d | строк %6d' % (nm, len(inn_po_prichine[k]), strok_po_prichine[k]))
print('  (чем именно сработало каждое слово — прогон `slova`)')
print('  продавец/сервис: сработали ТОЛЬКО слова БЕЗ предмета   %6d из %d'
      % (len(prod_bez_predmeta), len(inn_po_prichine['prod'])))
print('     · из них ПЕРВЫЙ ОКВЭД производственный (это завод)  %6d'
      % len(prod_bez_predmeta_zavod))
print('\n  --- пересечение с полем is_competitor')
print('  поле знает ИНН                                %6d' % len(inn_po_prichine['konk']))
print('  подозрительных, которых поле НЕ знает         %6d'
      % len(podozr - inn_po_prichine['konk']))
for k, nm in PRICHINY:
    if k == 'konk':
        continue
    peres = len(inn_po_prichine[k] & inn_po_prichine['konk'])
    print('  %-42s из них поле знает %5d' % (nm, peres))
print('\n  --- ПУСТОЕ ОПИСАНИЕ ДЕЯТЕЛЬНОСТИ (по нему судят текстовые причины)')
print('  у подозрительных описания НЕТ вовсе       %6d из %6d'
      % (pusto_act_vsego, len(zapis)))
print('  описание есть, но это ЗАГЛУШКА («не определено», «контент не получен») %5d'
      % zaglushka_act)
print('  итого судить по описанию НЕ ПО ЧЕМУ       %6d из %6d'
      % (pusto_act_vsego + zaglushka_act, len(zapis)))
for k, nm in PRICHINY:
    print('  %-42s без описания %5d из %5d'
          % (nm, pusto_act_po_prichine[k], len(inn_po_prichine[k])))
print('\n  --- СЛАБАЯ ПРИЧИНА ОДНА, БЕЗ СИЛЬНЫХ')
print('  только ОКВЭД, ни одной ТЕКСТОВОЙ сильной (продавец/подрядчик/НИИ) %6d'
      % len(tolko_slabaya))
print('  из них ещё и без is_competitor и без «машина в названии»          %6d'
      % len(tolko_slabaya_strogo))
print('  из них okved_all ПУСТ: известен ОДИН код, судить не по чему       %6d'
      % slab_bez_spiska)
print('  из них список кодов известен                                      %6d'
      % slab_so_spiskom)
print('     · в списке ЕСТЬ производственный код (слабая ЛОЖНА)            %6d'
      % len(slab_s_proizv))
print('     · в списке ТОЛЬКО торговля/услуги (слабая честна)              %6d'
      % slab_spisok_tolko_torg)
print('       сходится: %d + %d = %d, проверяемых %d'
      % (len(slab_s_proizv), slab_spisok_tolko_torg,
         len(slab_s_proizv) + slab_spisok_tolko_torg, slab_so_spiskom))
print('  из них заводское слово в НАЗВАНИИ                                 %6d'
      % len(slab_zavod_imya))
print('     · твёрдое («ЗАВОД», комбинат, ГОК, металлург)                  %6d'
      % imya_tverdo)
print('     · мягкое («научно-производственное», машиностроительная)       %6d'
      % imya_myagko)
print('  из них «производство/добыча/переработка» в ОПИСАНИИ               %6d'
      % len(slab_zavod_deyat))
print('\n  --- ГИПОТЕЗА ВЛАДЕЛЬЦА: у завода торговый ОКВЭД 46.x/47.x основной')
print('  «только слабая» с ПЕРВЫМ кодом 46.x/47.x                          %6d' % torg4647)
print('     · из них список кодов известен                                 %6d'
      % torg4647_spisok)
print('     · из них в списке ЕСТЬ производственный код                    %6d  (%s)'
      % (torg4647_proizv,
         ('%.0f%% проверяемых' % (100.0 * torg4647_proizv / torg4647_spisok))
         if torg4647_spisok else 'проверить не на чем'))
print('  (ОКВЭД по двум цифрам — прогон `slova`)')
print('ИТОГ ' + json.dumps(
    {'подозрительных ИНН': len(podozr),
     'поле is_competitor': len(inn_po_prichine['konk']),
     'только слабая ОКВЭД': len(tolko_slabaya),
     'из них с производственным кодом': len(slab_s_proizv),
     'раздел': CHAST}, ensure_ascii=False))
