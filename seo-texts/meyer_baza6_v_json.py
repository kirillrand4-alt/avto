# -*- coding: utf-8 -*-
"""Файл 6 Meyer (поиск по сайтам, 08.10) -> JSON для заливки в панель как «База 6».

Решение владельца (вариант А): все компании с номером ЛПР Meyer + крупные (выручка от
1,5 млрд), у которых есть только общие и рабочие номера (выход на ЛПР через коммутатор).
Компании, уже стоящие в Базе 1, не дублируются: им добавляется метка «База 6» и новые
номера («база одна, наполняется из разных источников»). Файлы Meyer 2–5 не учитываются
(владелец: «пока не трогаем»), колонка «Есть в файлах Meyer» только сохраняется.

ПРИОРИТЕТ (moy_prioritet) – та же шкала, что у Базы 1, чтобы базы честно перемешались в
очереди по баллу:
  выручка          0..40 – 10 x lg(выручка / 10 млн)
  попадание        20    – все отобраны по ОСНОВНОМУ ОКВЭД
  лучший контакт   ЛПР: руководитель, инженер, технолог, производство, качество 20,
                   закупки 15; +10 ФИО; +5 мобильный / +3 рабочий с добавочным;
                   +5 сайт подтверждён (ИНН на сайте или подтверждён моделью).
                   Без ЛПР: приёмная / общий номер 5, иначе 0.
  ещё ЛПР          5 за каждого сверх первого, не больше 10
Панель сверху добавит свои надбавки (телефон, закупщик, техник, ОКВЭД производства).

ХОЛДИНГИ: группа = общий номер у разных ИНН ИЛИ одно название холдинга (колонка агента),
по всему файлу. Группа целиком уходит одному продавцу; в карточке – список группы.

ВСЕ НОМЕРА компании грузятся («разделять, а не отсеивать»): ЛПР – наверху карточки, прочие
(продажи, бухгалтерия, общий номер…) – в «остальных» с видом номера. У компаний без ЛПР
наверху приёмная и общий номер – это и есть путь к ЛПР.
"""
import collections
import html
import json
import math
import re
import sys

import pandas as pd

VHOD, BAZA1_JSON, VYHOD = sys.argv[1], sys.argv[2], sys.argv[3]
x = pd.ExcelFile(VHOD)
K = x.parse('Компании', dtype=str)
C = x.parse('Контакты', dtype=str)
P = x.parse('Пояснения агентов', dtype=str)


def s(v):
    if v is None or (isinstance(v, float) and math.isnan(v)) or (not isinstance(v, str) and pd.isna(v)):
        return ''
    return html.unescape(str(v)).strip()


def chislo(v):
    try:
        return float(s(v).replace(' ', '').replace(',', '.'))
    except ValueError:
        return None


def cif(v):
    d = re.sub(r'\D', '', s(v))
    return d[-10:] if len(d) >= 10 else ''


inn1 = set()


def obhod(o):
    if isinstance(o, dict):
        for kk, v in o.items():
            if kk.lower() == 'inn' and v:
                inn1.add(str(v).strip())
            else:
                obhod(v)
    elif isinstance(o, list):
        for v in o:
            obhod(v)


obhod(json.load(open(BAZA1_JSON, encoding='utf-8')))

ROLI = {'закупки/снабжение': 'закупки', 'первое лицо/заместитель': 'директор/руководитель'}
TEH = {'главный инженер', 'технический директор', 'главный технолог', 'технолог', 'производство'}
SILNYE = TEH | {'директор/руководитель', 'качество'}
KOMMUTATOR = {'приёмная', 'общий номер', 'общий номер холдинга'}

kont_po = collections.defaultdict(list)
for _, r in C.iterrows():
    kont_po[s(r['ИНН'])].append(r)
pojasn = {s(r['ИНН']): s(r['Пояснение агента']) for _, r in P.iterrows()}


def rol(r):
    v = s(r['Роль'])
    return ROLI.get(v, v)


def lpr(r):
    return s(r['ЛПР Meyer']) == 'да'


def ball_kontakta(r, est_lpr):
    mob, dob = s(r['Мобильный']), s(r['Добавочный'])
    if lpr(r):
        b = 20 if rol(r) in SILNYE else 15 if rol(r) == 'закупки' else 10
        if s(r['ФИО']):
            b += 10
        b += 5 if mob else 3 if dob else 0
    else:
        b = 5 if (not est_lpr and s(r['Роль']) in KOMMUTATOR) else 0
    pr = s(r['Проверка номера'])
    if 'ИНН компании на сайте' in pr or 'подтверждён' in pr:
        b += 5
    return b


# ------------------------------------------------------------------ отбор (вариант А)
vybor, sliyanie = [], []
for _, c in K.iterrows():
    inn = s(c['ИНН'])
    ks = kont_po.get(inn, [])
    n_lpr = sum(1 for r in ks if lpr(r))
    n_mob = sum(1 for r in ks if s(r['Мобильный']))
    vyr = chislo(c['Выручка, руб'])
    if n_lpr:
        uroven = 'ЛПР мобильный' if any(lpr(r) and s(r['Мобильный']) for r in ks) else \
            'ЛПР рабочий с добавочным' if any(lpr(r) and s(r['Добавочный']) for r in ks) else 'ЛПР рабочий'
    elif ks and not n_mob and vyr and vyr >= 1.5e9:
        uroven = 'крупная, только общие номера'
    elif ks and vyr and vyr >= 1.5e9:
        # владелец 08.10 («добавь»): крупные без ЛПР, у которых кроме общих есть мобильные
        uroven = 'крупная, без ЛПР, есть мобильные'
    else:
        continue
    (sliyanie if inn in inn1 else vybor).append((c, ks, uroven))
print('отобрано: новых %d, уже в Базе 1 (слияние) %d' % (len(vybor), len(sliyanie)))
print('   по уровню:', collections.Counter(u for _, _, u in vybor).most_common())

# ------------------------------------------------------------------ холдинги (по всему файлу)
roditel = {}


def koren(a):
    roditel.setdefault(a, a)
    while roditel[a] != a:
        roditel[a] = roditel[roditel[a]]
        a = roditel[a]
    return a


def soedinit(a, b):
    roditel[koren(a)] = koren(b)


# «Чем связана» – коротко: число общих номеров, а не их список (у MLK Group их 11 подряд)
obshchih = collections.Counter()
po_holdingu = set()
po_nomeru = collections.defaultdict(set)
for _, r in C.iterrows():
    k10 = cif(r['Мобильный'] if s(r['Мобильный']) else r['Рабочий'])
    if k10:
        po_nomeru[k10].add(s(r['ИНН']))
for k10, inns in po_nomeru.items():
    if len(inns) > 1:
        inns = sorted(inns)
        for i in inns:
            obshchih[i] += 1
        for i in inns[1:]:
            soedinit(inns[0], i)


def svyaz_tekst(inn):
    chasti = []
    if obshchih[inn]:
        chasti.append('общих номеров с группой: %d' % obshchih[inn])
    if inn in po_holdingu:
        chasti.append('холдинг по сайту')
    return ', '.join(chasti)


def norm_h(h):
    h = s(h).lower()
    h = re.sub(r'\(.*?\)', ' ', h)
    h = re.sub(r'\b(ооо|ао|пао|зао|оао|гк|группа компаний|холдинг|агрохолдинг)\b', ' ', h)
    h = re.sub(r'[«»"\'“”„.,]', ' ', h)
    return ' '.join(h.split())


po_h = collections.defaultdict(list)
for _, c in K.iterrows():
    if norm_h(c['Холдинг (агент)']):
        po_h[norm_h(c['Холдинг (агент)'])].append(s(c['ИНН']))
for h, inns in po_h.items():
    for i in inns:
        po_holdingu.add(i)
    for i in inns[1:]:
        soedinit(inns[0], i)
gruppy_vse = collections.defaultdict(list)
for _, c in K.iterrows():
    gruppy_vse[koren(s(c['ИНН']))].append(c)
vybrannye = {s(c['ИНН']) for c, _, _ in vybor + sliyanie}
gruppy = {}
for g, chleny in gruppy_vse.items():
    if len(chleny) < 2 or not any(s(c['ИНН']) in vybrannye for c in chleny):
        continue
    imena = collections.Counter(re.sub(r'\s*\(не подтверждено цитатой\)', '', s(c['Холдинг (агент)']))
                                for c in chleny if s(c['Холдинг (агент)']))
    gid = 'g' + min(s(c['ИНН']) for c in chleny)
    gruppy[gid] = {
        'nazvanie': imena.most_common(1)[0][0] if imena else '',
        'chleny': [{'inn': s(c['ИНН']), 'nazvanie': s(c['Название']), 'region': s(c['Регион']),
                    'segment': s(c['Сегмент']), 'vyruchka_rub': chislo(c['Выручка, руб']),
                    'v_vybore': s(c['ИНН']) in vybrannye, 'svyaz': svyaz_tekst(s(c['ИНН']))}
                   for c in sorted(chleny, key=lambda c: -(chislo(c['Выручка, руб']) or 0))]}
gruppa_inn = {ch['inn']: gid for gid, g in gruppy.items() for ch in g['chleny']}
print('групп-холдингов с отобранными: %d (%s)' % (len(gruppy), collections.Counter(
    sum(ch['v_vybore'] for ch in g['chleny']) for g in gruppy.values()).most_common()))

# ------------------------------------------------------------------ компании и контакты
kompanii, kontakty = [], []
for c, ks, uroven in vybor + sliyanie:
    inn = s(c['ИНН'])
    est_lpr = any(lpr(r) for r in ks)
    lprs = [r for r in ks if lpr(r)]
    luchshiy = max(ks, key=lambda r: ball_kontakta(r, est_lpr)) if ks else None
    vyr = chislo(c['Выручка, руб'])
    b_vyr = max(0.0, min(40.0, 10 * math.log10(vyr / 1e7))) if vyr and vyr > 0 else 0.0
    b_pop = 20
    b_kont = ball_kontakta(luchshiy, est_lpr) if luchshiy is not None else 0
    b_esche = min(10, 5 * max(0, len(lprs) - 1))
    ball = round(b_vyr + b_pop + b_kont + b_esche, 1)
    pochemu = 'выручка %+.0f · попадание %+d · лучший контакт %+d · ещё ЛПР %+d = %.1f' % (
        b_vyr, b_pop, b_kont, b_esche, ball)
    roli = []
    for r in lprs:
        if rol(r) not in roli:
            roli.append(rol(r))

    def nomer(r):
        mob, rab, dob = s(r['Мобильный']), s(r['Рабочий']), s(r['Добавочный'])
        dob = dob[:-2] if dob.endswith('.0') else dob
        # в части строк добавочный уже записан в самом рабочем номере – второй раз не дописываем
        return mob or (rab + (' доб. %s' % dob if dob and not re.search(r'доб', rab, re.I) else ''))
    if lprs:
        lk = max(lprs, key=lambda r: ball_kontakta(r, True))
        lpr_kratko = ' · '.join(v for v in (s(lk['ФИО']), s(lk['Должность']) or rol(lk), nomer(lk)) if v)
        if len(lprs) > 1:
            lpr_kratko += ' (+ ещё %d)' % (len(lprs) - 1)
    else:
        lk = luchshiy
        lpr_kratko = ('ЛПР не найден, через коммутатор: %s' if s(lk['Роль']) in KOMMUTATOR
                      else 'ЛПР не найден, номер с сайта: %s') % ' · '.join(
            v for v in (s(lk['Роль']) if s(lk['Роль']) != 'без подписи' else '', nomer(lk)) if v)
        n_mob_bez = sum(1 for r in ks if s(r['Мобильный']))
        if n_mob_bez:
            lpr_kratko += ' (мобильных без ЛПР: %d)' % n_mob_bez
    osn = s(c['Основной ОКВЭД'])
    dop = [v.strip() for v in s(c['Доп. ОКВЭД']).split(',') if v.strip()]
    sayt = s(c['Сайт'])
    kompanii.append({
        'inn': inn, 'sliyanie': inn in inn1, 'predpriyatie': s(c['Название']), 'region': s(c['Регион']),
        'sayt': sayt, 'okved': osn, 'okvedy_vse': ' | '.join([osn] + [d for d in dop if d != osn]),
        'opisanie': s(c['Описание (по сайту)']) or pojasn.get(inn, ''),
        'produkciya': s(c['Продукция']), 'moshchnosti': s(c['Мощности']),
        'vyruchka_rub': vyr, 'fin_god': '2025' if 'ФНС' in s(c['Откуда выручка']) else '',
        'segment': s(c['Сегмент']), 'segment_osn': s(c['Сегмент']), 'popadanie': 'основной ОКВЭД',
        'lpr_kratko': lpr_kratko, 'lpr_roli': ', '.join(roli),
        'moy_prioritet': ball, 'prioritet_pochemu': pochemu, 'kachestvo_nomera': uroven,
        'n_phones': len(ks), 'has_phone': int(bool(ks)),
        'n_purchaser': sum(1 for r in lprs if rol(r) == 'закупки'),
        'n_tech': sum(1 for r in lprs if rol(r) in TEH),
        'lpr_mobilnyy': int(any(s(r['Мобильный']) for r in lprs)),
        'lpr_s_fio': sum(1 for r in lprs if s(r['ФИО'])),
        'bitrix_fajl': s(c['Есть контакт в Битрикс']),
        'holding': (gruppy.get(gruppa_inn.get(inn), {}) or {}).get('nazvanie') or s(c['Холдинг (агент)']),
        'holding_gruppa': gruppa_inn.get(inn, ''),
        'v_fajlah_meyer': s(c['Есть в файлах Meyer']), 'razdel_kc': s(c['Раздел']),
        'sayt_chey': s(c['Сайт: чей']), 'otkuda_kompaniya': s(c['Откуда компания']),
        'ssylki_na_istochniki': ' | '.join(sorted({s(r['Ссылка на источник']) for r in ks if s(r['Ссылка на источник'])})),
    })
    for r in ks:
        mob = s(r['Мобильный'])
        dob = s(r['Добавочный'])
        dob = dob[:-2] if dob.endswith('.0') else dob
        vid_roli = s(r['Роль'])
        je_lpr = lpr(r)
        naverh = je_lpr or (not est_lpr and vid_roli in KOMMUTATOR)
        kontakty.append({
            'inn': inn, 'value': nomer(r), 'kind': 'phone',
            'person': s(r['ФИО']) or None,
            'role': rol(r) if je_lpr else ('' if vid_roli == 'без подписи' else vid_roli),
            'position': s(r['Должность']),
            'phone_type': 'мобильный' if mob else 'рабочий с добавочным' if dob else 'рабочий',
            'source': ' · '.join(v for v in (s(r['Источник']), s(r['Проверка номера'])) if v),
            'source_url': s(r['Ссылка на источник']) or None,
            'fragment': s(r['Фрагмент страницы'])[:400],
            'is_purchaser': int(je_lpr and rol(r) == 'закупки'), 'is_tech': int(je_lpr and rol(r) in TEH),
            'has_role': int(naverh),
            # вид неличного номера: такие уходят в «остальные» карточки, но не теряются
            'nomer_ne_lichnyy': None if naverh else (vid_roli or 'без подписи'),
            'lpr': int(je_lpr), 'cifry': cif(mob or s(r['Рабочий'])),
        })
json.dump({'kompanii': kompanii, 'kontakty': kontakty, 'gruppy': gruppy,
           'fajl': '6-meyer-poisk-0810.xlsx', 'baza': 'База 6',
           'baza_opisanie': 'поиск по сайтам: молоко, сыры, мясо, хлеб, корма (08.10)'},
          open(VYHOD, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('компаний %d (из них слияние с Базой 1: %d), контактов %d -> %s' % (
    len(kompanii), sum(k['sliyanie'] for k in kompanii), len(kontakty), VYHOD))
print('   номеров ЛПР %d, наверху у компаний без ЛПР (коммутатор) %d, в «остальных» %d' % (
    sum(k['lpr'] for k in kontakty), sum(1 for k in kontakty if k['has_role'] and not k['lpr']),
    sum(1 for k in kontakty if not k['has_role'])))
bally = sorted((k['moy_prioritet'] for k in kompanii), reverse=True)
print('балл: макс %.1f, медиана %.1f, мин %.1f' % (bally[0], bally[len(bally) // 2], bally[-1]))
for k in sorted(kompanii, key=lambda z: -z['moy_prioritet'])[:3] + sorted(kompanii, key=lambda z: z['moy_prioritet'])[:2]:
    print('   %-40s %-28s %s' % (k['predpriyatie'][:40], k['kachestvo_nomera'], k['prioritet_pochemu']))
print('с описанием %d, продукцией %d, мощностями %d, в битриксе (по файлу) %d, в холдинге %d' % (
    sum(bool(k['opisanie']) for k in kompanii), sum(bool(k['produkciya']) for k in kompanii),
    sum(bool(k['moshchnosti']) for k in kompanii), sum(bool(k['bitrix_fajl']) for k in kompanii),
    sum(bool(k['holding_gruppa']) for k in kompanii)))
print('телефоны с добавочным:', sum(1 for k in kontakty if 'доб.' in k['value']), 'пример:',
      next((k['value'] for k in kontakty if 'доб.' in k['value']), ''))
