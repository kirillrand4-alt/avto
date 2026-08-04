# -*- coding: utf-8 -*-
"""Должность лежит на той же странице, что и почта — прямо над ней. Мы её не взяли.

ОТКУДА ЗАДАЧА. Владелец показал карточку ООО «Ставролен» и рядом — саму страницу
`stavrolen.lukoil.ru/ru/Contacts`. На странице:

    УПРАВЛЕНИЕ МТО И РЕАЛИЗАЦИИ МТР
      Начальник управления
      NovikovaOT@lukoil.com
      +7 8655 95 15 65

В панели тот же человек стоит как «Новикова О.Т. — общий», без должности и без номера.
То есть должность и телефон были НА ТОЙ ЖЕ СТРАНИЦЕ, ссылку на которую мы сохранили, а
обход забрал только почту и вывел имя из неё.

Это класс, а не случай: корпоративная страница контактов почти всегда построена так —
заголовок подразделения, под ним должность, под ней почта и телефон. Замер по нашему файлу:
**400 человек на 82 предприятиях без должности, 396 из них без телефона, 129 страниц**.

ЧЕГО МОДУЛЬ НЕ ДЕЛАЕТ. Он не угадывает: должность берётся только если найдена в ОКНЕ перед
почтой и после предыдущей почты на той же странице (иначе заголовок соседнего блока налипнет
на чужого человека). Всё, что взято, пишется вместе с куском страницы, по которому взято, —
чтобы проверяющий не верил на слово.

Использование:
    python3 dolzhnosti_s_kontaktnyh_stranic.py --parallel 6
    python3 dolzhnosti_s_kontaktnyh_stranic.py --stranic 5      # пробный прогон
"""
import csv
import html as _html
import json
import os
import re
import subprocess
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
KLIENT = os.path.join(BAZA, 'server', 'run_on_server.py')
L = os.path.join(BAZA, 'engineers-lens')
C = os.path.join(L, 'centro')
VHOD = os.path.join(C, 'LICA-S-SAJTOV-SO-SSYLKAMI.csv')
VYHOD = os.path.join(C, 'LICA-S-SAJTOV-DOLZHNOSTI.csv')
COLS = ['inn', 'predpriyatie', 'imya', 'pochta', 'dolzhnost_nayden', 'telefon_nayden',
        'podrazdelenie_nayden', 'ssylka', 'kusok_stranicy', 'pochemu']

DOLZHNOST = re.compile(
    r'(?:^|[\n>·•|])\s*((?:и\.?\s*о\.?\s*)?(?:первый\s+)?(?:заместител\w+\s+)?'
    r'(?:начальник\w*|директор\w*|руководител\w*|главн\w+\s+\w+|ведущ\w+\s+\w+|'
    r'зам\.?\s*\w+|менеджер\w*|специалист\w*|инженер\w*|технолог\w*|энергетик\w*|механик\w*)'
    r'[^\n>·•|]{0,80})', re.I)
TELEFON = re.compile(r'(?:\+7|8)[\s\-()]*\d[\d\s\-()]{8,16}\d')
# Заголовок подразделения бывает и КАПСОМ («ОТДЕЛ ПОСТАВОК»), и обычным регистром
# («Управление МТО и реализации МТР»). Первая версия брала только капс — и по Ставролену
# вернула «Начальник отдела» пять раз подряд без указания, какого именно отдела.
# Должность без подразделения продавцу почти бесполезна: он не знает, к кому попал.
ZAGOLOVOK = re.compile(
    r'(?:^|\n)\s*((?:[А-ЯЁ][А-ЯЁ \-«»,./0-9]{6,70})'
    r'|(?:(?:управлени|отдел|департамент|служб|дирекци|группа|сектор|цех|центр)\w*'
    r'[^\n]{0,60}))\s*(?:\n|$)', re.I)


def dovod(imya, po_umolchaniyu):
    return type(po_umolchaniyu)(sys.argv[sys.argv.index(imya) + 1]) \
        if imya in sys.argv else po_umolchaniyu


def chitat(put):
    return list(csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(put) else []


def v_tekst(h):
    """HTML → текст с сохранением переводов строк: разбор опирается на СТРОКИ, а не на теги."""
    t = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', h or '')
    t = re.sub(r'(?i)<br\s*/?>|</(p|div|li|tr|h[1-6]|td)>', '\n', t)
    t = re.sub(r'<[^>]+>', ' ', t)
    t = _html.unescape(t)
    # Ноль-ширинный пробел \u200b стоит на сайтах ЛУКОЙЛа ПЕРЕД словом «Начальник» и ломает
    # привязку выражения к началу строки: «\u200bНачальник управления» не считалось должностью,
    # хотя оно там написано. Невидимый знак — худший сорт помехи: глазами его нет.
    t = t.replace('\u200b', '').replace('\ufeff', '')
    t = re.sub(r'[ \t\xa0]+', ' ', t)
    return re.sub(r'\n{2,}', '\n', t)


def stranica(url, tayminaut=400):
    zad = {'url': url, 'screenshot': False, 'proxy': '', 'return_html': True,
           'html_cap': 900000, 'wait_ms': 4000}
    try:
        p = subprocess.run([sys.executable, KLIENT, 'browser_probe',
                            json.dumps(zad, ensure_ascii=False)],
                           capture_output=True, text=True, timeout=tayminaut)
    except subprocess.TimeoutExpired:
        return None, f'раннер не ответил за {tayminaut} с'
    try:
        d = json.loads(p.stdout[p.stdout.index('{'):]).get('data') or {}
    except (ValueError, json.JSONDecodeError):
        return None, (p.stdout or p.stderr or 'пустой ответ')[-200:]
    h = d.get('html') or ''
    if not h:
        return None, f"тело пусто, http_status={d.get('http_status')}, error={str(d.get('error'))[:90]}"
    return v_tekst(h), ''


def razobrat(tekst, pochty):
    """Для каждой почты — должность ПЕРЕД ней и телефон ПОСЛЕ. Возвращает {почта: словарь}."""
    nizhniy = tekst.lower()
    mesta = sorted(((nizhniy.find(p.lower()), p) for p in pochty if p), key=lambda x: x[0])
    itog = {}
    predydushchiy_konec = 0
    for i, (poz, p) in enumerate(mesta):
        if poz < 0:
            itog[p] = {'pochemu': 'почты нет на странице — страница изменилась или ссылка не та'}
            continue
        # Окно перед почтой ограничено предыдущей почтой: иначе заголовок чужого блока
        # налипнет на этого человека. Это главный заслон от выдумки.
        nachalo = max(predydushchiy_konec, poz - 400)
        do = tekst[nachalo:poz]
        posle = tekst[poz:poz + 250]
        predydushchiy_konec = poz + len(p)
        d = DOLZHNOST.findall(do)
        z = ZAGOLOVOK.findall(do)
        tel = TELEFON.findall(posle)
        itog[p] = {
            'dolzhnost_nayden': (d[-1].strip() if d else ''),
            'podrazdelenie_nayden': (z[-1].strip() if z else ''),
            'telefon_nayden': (tel[0].strip() if tel else ''),
            'kusok_stranicy': re.sub(r'\s+', ' ', do[-160:] + ' >>> ' + p),
            'pochemu': ('' if d else 'должности в окне перед почтой нет'),
        }
    return itog


def main():
    parallel = dovod('--parallel', 6)
    import predel_rannera
    predel_rannera.preduprezhdenie(parallel)
    rows = [r for r in chitat(VHOD)
            if not (r.get('dolzhnost') or '').strip()
            and (r.get('ssylka') or '').startswith('http')
            and (r.get('pochta') or '').strip()]
    po_stranicam = defaultdict(list)
    for r in rows:
        po_stranicam[r['ssylka']].append(r)
    celi = list(po_stranicam)[:dovod('--stranic', 10 ** 6)]
    print(f'людей без должности {len(rows)} на {len(po_stranicam)} страницах; '
          f'в этот прогон {len(celi)}', file=sys.stderr)

    novyy = not os.path.exists(VYHOD) or os.path.getsize(VYHOD) == 0
    f = open(VYHOD, 'a', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=COLS, delimiter=';', extrasaction='ignore')
    if novyy:
        w.writeheader()
    sch = {'страниц': 0, 'сбоев': 0, 'должностей': 0, 'телефонов': 0}
    lock = threading.Lock()

    def odna(url):
        tekst, err = stranica(url)
        if err:
            return url, None, err
        return url, razobrat(tekst, [r['pochta'].strip() for r in po_stranicam[url]]), ''

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for n, (url, najdeno, err) in enumerate(pool.map(odna, celi), 1):
            with lock:
                sch['страниц'] += 1
                if err:
                    sch['сбоев'] += 1
                    for r in po_stranicam[url]:
                        w.writerow({**r, 'pochemu': f'страница не снялась: {err[:80]}'})
                else:
                    for r in po_stranicam[url]:
                        x = najdeno.get(r['pochta'].strip(), {})
                        if x.get('dolzhnost_nayden'):
                            sch['должностей'] += 1
                        if x.get('telefon_nayden'):
                            sch['телефонов'] += 1
                        w.writerow({**r, **x})
                f.flush()
                if n % 5 == 0:
                    print(f'  {n}/{len(celi)}: {sch}', file=sys.stderr, flush=True)
    f.close()
    print(f'готово: {sch}\n→ {VYHOD}', file=sys.stderr)


if __name__ == '__main__':
    main()
