# -*- coding: utf-8 -*-
"""Страница «Структурные подразделения» — ФИО, должность и ПРЯМОЙ телефон подряд.

ОТКУДА ЗАДАЧА. Владелец открыл `kaustik.ru/ru/contacts/strukturnye-podrazdeleniya/` и сказал:
«единственная страница, откуда надо было вытянуть контакты, но они не вытянуты». Он прав.
На ней лежит ровно то, за чем мы охотимся:

    Управление материально-технического обеспечения
      Куксина Светлана Владимировна
      Директор по закупкам
      +7 (8442) 40-64-68
      Демченко Максим Петрович
      Заместитель директора по закупкам по МТО производства, ремонтов и ТО
      +7 (8442) 40-67-37

Имя, должность целиком и ПРЯМОЙ номер — не приёмная. Прежний обход сайтов брал страницы
«Контакты» и «Руководство» и работал ОТ ПОЧТЫ: находил адрес и смотрел, что рядом. Здесь
почт почти нет, есть телефоны, и от почты плясать нельзя — страница проходила мимо.

ЧЕМ ЭТОТ РАЗБОР ОТЛИЧАЕТСЯ. Он идёт не от почты, а от ФИО: строка вида «Фамилия Имя
Отчество» на отдельной строке, под ней должность, под ней телефон и/или почта. Заголовок
подразделения запоминается сверху и приписывается людям под ним.

ЧЕГО НЕ ДЕЛАЕТ. Не угадывает должность, если её нет; не приписывает человеку номер, стоящий
дальше следующего человека; не ходит по ссылкам вглубь — только по заданным путям.

Использование:
    python3 kontakty_strukturnyh_podrazdeleniy.py --sajt kaustik.ru
    python3 kontakty_strukturnyh_podrazdeleniy.py --vse --parallel 4
"""
import csv
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dolzhnosti_s_kontaktnyh_stranic as D

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
C = os.path.join(L, 'centro')
OCHERED = os.path.join(L, 'OCHERED-centrobezhnye.csv')
VYHOD = os.path.join(C, 'LICA-STRUKTURNYE-PODRAZDELENIYA.csv')
COLS = ['inn', 'predpriyatie', 'podrazdelenie', 'chelovek', 'dolzhnost', 'telefon', 'pochta',
        'sajt', 'stranica', 'pochemu']

# Пути, по которым такие страницы лежат чаще всего. Список из наблюдений, а не из головы:
# первый — тот самый, что показал владелец.
PUTI = [
    '/ru/contacts/strukturnye-podrazdeleniya/', '/contacts/strukturnye-podrazdeleniya/',
    '/kontakty/strukturnye-podrazdeleniya/', '/struktura/', '/structure/',
    '/ru/contacts/', '/contacts/', '/kontakty/', '/contacts/contacts/',
    '/about/rukovodstvo/', '/ru/about/rukovodstvo/', '/rukovodstvo/', '/company/management/',
]

FIO = re.compile(r'^([А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё\-]{4,})$')
DOLZH = re.compile(r'^[А-ЯЁа-яё][А-ЯЁа-яё \-,.()«»/0-9]{4,140}$')
TEL = re.compile(r'(?:\+7|8)[\s\-()]*\d[\d\s\-()]{8,16}\d')
POCHTA = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
# Заголовок подразделения: «Управление логистики», «Отдел главного механика», «Дирекция по …»
ZAGOL = re.compile(r'^((?:управлени|отдел|департамент|служб|дирекци|группа|сектор|цех|центр|'
                   r'производств|дивизион)\w*[^\n]{0,70})$', re.I)
NE_DOLZHNOST = re.compile(r'^\s*(?:контакт|адрес|телефон|почта|e-?mail|факс|главная|'
                          r'подробнее|читать|версия|поиск|меню|войти)', re.I)


def razobrat_stranicu(tekst):
    """Текст страницы → список словарей. Идём ОТ ФИО, а не от почты."""
    stroki = [s.strip() for s in (tekst or '').split('\n')]
    lyudi, podrazd = [], ''
    for i, s in enumerate(stroki):
        z = ZAGOL.match(s)
        if z and not FIO.match(s):
            podrazd = z.group(1).strip()
            continue
        if not FIO.match(s):
            continue
        okno = [x for x in stroki[i + 1:i + 6] if x]
        dolzh, tel, poc = '', '', ''
        for x in okno:
            if FIO.match(x):
                break                      # начался следующий человек — чужое не берём
            if not tel:
                m = TEL.search(x)
                if m:
                    tel = m.group(0).strip()
            if not poc:
                m = POCHTA.search(x)
                if m:
                    poc = m.group(0)
            if not dolzh and DOLZH.match(x) and not NE_DOLZHNOST.match(x) \
                    and not TEL.search(x) and not POCHTA.search(x):
                dolzh = x
        if dolzh or tel or poc:
            lyudi.append({'chelovek': s, 'dolzhnost': dolzh[:120], 'telefon': tel,
                          'pochta': poc, 'podrazdelenie': podrazd[:70]})
    return lyudi


def main():
    parallel = D.dovod('--parallel', 4)
    import predel_rannera
    predel_rannera.preduprezhdenie(parallel)
    odin = D.dovod('--sajt', '')
    if odin:
        celi = [{'inn': '', 'predpriyatie': '', 'sayt': odin}]
    else:
        celi = [r for r in D.chitat(OCHERED) if (r.get('sayt') or '').strip()]
        celi = celi[:D.dovod('--predpriyatiy', 10 ** 6)]
    print(f'предприятий с сайтом: {len(celi)}', file=sys.stderr)

    novyy = not os.path.exists(VYHOD) or os.path.getsize(VYHOD) == 0
    f = open(VYHOD, 'a', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=COLS, delimiter=';', extrasaction='ignore')
    if novyy:
        w.writeheader()
    sch = {'сайтов': 0, 'страниц снято': 0, 'людей': 0, 'с телефоном': 0, 'пусто': 0}
    lock = threading.Lock()

    def odin_sajt(r):
        sajt = (r.get('sayt') or '').strip().rstrip('/')
        if not sajt.startswith('http'):
            sajt = 'https://' + sajt
        najdeno, snyato = [], 0
        for put in PUTI:
            t, err = D.stranica(sajt + put, tayminaut=300)
            if err or not t:
                continue
            snyato += 1
            lyudi = razobrat_stranicu(t)
            if lyudi:
                for x in lyudi:
                    najdeno.append(dict(x, stranica=sajt + put))
                # Нашли страницу с людьми — дальше по этому сайту не ходим: остальные пути
                # дадут тех же людей другим списком, а раннер не бесконечный.
                break
        return r, najdeno, snyato

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for n, (r, najdeno, snyato) in enumerate(pool.map(odin_sajt, celi), 1):
            with lock:
                sch['сайтов'] += 1
                sch['страниц снято'] += snyato
                if not najdeno:
                    sch['пусто'] += 1
                for x in najdeno:
                    sch['людей'] += 1
                    if x['telefon']:
                        sch['с телефоном'] += 1
                    w.writerow(dict(x, inn=r.get('inn', ''),
                                    predpriyatie=(r.get('predpriyatie') or '')[:60],
                                    sajt=r.get('sayt', ''),
                                    pochemu='страница структурных подразделений / контактов'))
                f.flush()
                if n % 5 == 0:
                    print(f'  {n}/{len(celi)}: {sch}', file=sys.stderr, flush=True)
    f.close()
    print(f'готово: {sch}\n→ {VYHOD}', file=sys.stderr)


if __name__ == '__main__':
    main()
