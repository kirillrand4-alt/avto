# -*- coding: utf-8 -*-
"""Пройти ВСЕ старые потоки починенным шаблоном: что потеряли пятизначные коды.

ПОЧЕМУ ЭТО НАДО СДЕЛАТЬ ЗАДНИМ ЧИСЛОМ И БЕСПЛАТНО. Прежний шаблон телефона требовал
код города из 3-4 цифр. Пятизначные коды — 81366 (Пикалёво), 35161 (Сатка), 3439
(Каменск-Уральский), 39550 (Шелехов) — в него не влезали, и номер рядом с фамилией
просто не замечался. Это не «не нашли»: страница была скачана, текст сохранён, номер
в нём стоял. Значит его можно достать СЕЙЧАС, не потратив ни одного запроса из общего
пула.

Замер на карточках площадки уже показал отдачу: из 1 644 непрочитанных карточек 574
закрылись одной этой починкой. Потоки обратного хода, добора и должностей не проверялись
вовсе — а в них лежат цитаты вокруг фамилий, то есть ровно тот текст, где номер и
должен стоять.

ЧТО СЧИТАЕТСЯ НАХОДКОЙ. Номер, которого НЕТ в уже добытых контактах этой записи (сверка
по цифрам, а не по написанию), стоящий в цитате не дальше 400 знаков от фамилии, и между
ним и фамилией нет ЧУЖОЙ фамилии. Те же три условия, что и в самом канале: задним числом
нельзя добывать мягче, чем добывалось вперёд, иначе выгрузка станет разносортной.

РАЗДЕЛЯТЬ, А НЕ ОТСЕИВАТЬ. Вид номера называется словом: личный мобильный, городской с
добавочным, городской, слабый (без слова связи рядом). Ничего не выбрасывается.
"""
import collections
import csv
import importlib.util
import io
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, r'C:\sender\_ops')
spec = importlib.util.spec_from_file_location(
    'tel', r'C:\sender\_ops\3s_p25_telefon_shablon.py')
TEL = importlib.util.module_from_spec(spec)
spec.loader.exec_module(TEL)

VYHOD = r'C:\sender\_ops\P25-PYATIZNACHNYE-VOZVRAT-3S-001.csv'
# поток, список, поле значения, поле человека
POTOKI = (
    (r'C:\sender\_ops\p25-obratnyy.jsonl',     'kontakty', 'znachenie', 'fio'),
    (r'C:\sender\_ops\p25-obratnyy-teh.jsonl', 'kontakty', 'znachenie', 'fio'),
    (r'C:\sender\_ops\p25-dobit.jsonl',        'naydeno',  'telefon',   'fio'),
    (r'C:\sender\_ops\p25-dolzhnost.jsonl',    'naydeno',  'telefony',  'chelovek'),
    (r'C:\sender\_ops\p25-nomer.jsonl',        'naydeno',  'nomer',     'fio'),
    (r'C:\sender\_ops\p25-dobavochnyy.jsonl',  'naydeno',  'nomer',     'chelovek'),
)
FAM = re.compile(r'\b([А-ЯЁ][а-яё]{3,})(?=\s+[А-ЯЁ])')


def chuzhaya_ryadom(tekst, poz, fam):
    """Ближайшая ЧУЖАЯ фамилия между номером и нашим человеком — тот же заслон, что в канале."""
    for m in FAM.finditer(tekst):
        f = m.group(1)
        if f.lower()[:6] == fam.lower()[:6]:
            continue
        if abs(m.start() - poz) <= 200:
            return f
    return ''


sch = collections.Counter()
stroki = []
for put, spisok, pole, pole_cheloveka in POTOKI:
    if not os.path.exists(put):
        continue
    for ln in open(put, encoding='utf-8'):
        try:
            z = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        if z.get('err'):
            continue
        fio = (z.get(pole_cheloveka) or z.get('fio') or z.get('chelovek') or '').strip()
        if not fio:
            continue
        fam = fio.split()[0]
        # Что уже добыто по этой записи — сверяем ЦИФРАМИ, а не написанием.
        uzhe = set()
        citaty = []
        for n in (z.get(spisok) or []):
            if not isinstance(n, dict):
                continue
            syroy = n.get(pole)
            for v in (syroy if isinstance(syroy, list) else [syroy]):
                c = TEL.cifry(v)
                if len(c) == 11:
                    uzhe.add(c)
            if n.get('citata'):
                citaty.append((n.get('citata'), n.get('ssylka', ''),
                               n.get('pochemu') or n.get('pochemu_stranica', '')))
        for citata, ssylka, pochemu in citaty:
            poz_fam = citata.lower().find(fam.lower())
            if poz_fam < 0:
                sch['фамилии в цитате нет — привязать не к чему'] += 1
                continue
            for n in TEL.nomera(citata):
                if n['cifry'] in uzhe:
                    continue
                rasst = abs(n['nachalo'] - poz_fam)
                if rasst > 400:
                    sch['номер вернулся, но дальше 400 знаков от фамилии'] += 1
                    continue
                chuzh = chuzhaya_ryadom(citata, n['nachalo'], fam)
                if chuzh:
                    sch['номер вернулся, но между ним и фамилией ЧУЖАЯ фамилия'] += 1
                    continue
                uzhe.add(n['cifry'])
                vid = ('ЛИЧНЫЙ МОБИЛЬНЫЙ' if n['mobilnyy']
                       else ('городской с добавочным %s' % n['dobavochnyy']
                             if n['dobavochnyy'] else 'городской'))
                if n['vid'] == 'слабый номер':
                    vid += ' (слабый: слова связи рядом нет)'
                sch['ВЕРНУЛСЯ: ' + vid.split(' (')[0]] += 1
                stroki.append({
                    'inn': z.get('inn', ''), 'predpriyatie': z.get('predpriyatie', ''),
                    'chelovek': fio, 'dolzhnost': z.get('dolzhnost', ''),
                    'telefon': n['kak_napisan'], 'telefon_ciframi': n['cifry'],
                    'dobavochnyy': n['dobavochnyy'], 'vid': vid,
                    'znakov_do_familii': rasst,
                    'pochemu_vernulsya': 'прежний шаблон не брал этот код города',
                    'chem_podtverzhdena': pochemu, 'ssylka': ssylka,
                    'citata': re.sub(r'\s+', ' ', citata)[:400],
                    'otkuda_potok': os.path.basename(put),
                })

# Один и тот же человек с одним номером мог прийти из двух цитат — склеиваем по цифрам.
vidano, chistye = set(), []
for s in stroki:
    k = (s['inn'], s['chelovek'].lower(), s['telefon_ciframi'])
    if k in vidano:
        continue
    vidano.add(k)
    chistye.append(s)

# Номер, встреченный у двух и более РАЗНЫХ людей, личным быть не может — помечаем.
na_baze = collections.defaultdict(set)
for s in chistye:
    na_baze[s['telefon_ciframi']].add(s['chelovek'].lower())
for s in chistye:
    n = len(na_baze[s['telefon_ciframi']])
    if n >= 2:
        s['vid'] += ' — ОБЩИЙ, на нём %d человек' % n

otvet = ''
if chistye:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(chistye[0].keys()), delimiter=';',
                       extrasaction='ignore')
    w.writeheader()
    w.writerows(chistye)
    open(VYHOD, 'w', encoding='utf-8-sig', newline='').write(buf.getvalue())
    url, tok = os.environ.get('DROP_URL', ''), os.environ.get('DROP_TOKEN', '')
    if url and tok:
        rq = urllib.request.Request(url.rstrip('/') + '/' + os.path.basename(VYHOD),
                                    data=buf.getvalue().encode('utf-8-sig'), method='PUT')
        rq.add_header('X-Drop-Token', tok)
        try:
            otvet = urllib.request.urlopen(rq, timeout=120).status
        except Exception as e:  # noqa: BLE001
            otvet = 'сбой: %s' % e

for s in chistye[:14]:
    print('  %-28s %-26s %-22s %s' % (s['predpriyatie'][:28], s['chelovek'][:26],
                                      s['telefon'][:22], s['vid'][:34]))
for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({
    'ВЕРНУЛОСЬ НОМЕРОВ': len(chistye),
    'из них личных мобильных': len([s for s in chistye if 'ЛИЧНЫЙ' in s['vid']
                                    and 'ОБЩИЙ' not in s['vid']]),
    'людей': len({(s['inn'], s['chelovek'].lower()) for s in chistye}),
    'предприятий': len({s['inn'] for s in chistye if s['inn']}),
    'файл': os.path.basename(VYHOD) if chistye else '', 'дроп': otvet}, ensure_ascii=False))
