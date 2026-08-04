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
    """Текст страницы → список словарей. Идём ОТ ФИО, а не от почты.

    ДОЛЖНОСТЬ БЫВАЕТ И СВЕРХУ. Первая версия искала её только НИЖЕ имени. На «Петербургском
    тракторном заводе» страница устроена наоборот:

        Зам. директора по качеству          ← должность
        Олешко Евгений Олегович             ← имя
        +7-911-020-02-84
        Начальник управления по гарантийно-сервисному обслуживанию   ← должность СЛЕДУЮЩЕГО
        Фомичев Владислав Викторович

    и каждый получал должность соседа снизу. Ошибка не шумит: строки настоящие, люди
    настоящие, должности настоящие — просто не те. «Зам. директора по качеству» уехал бы в
    технические ЛПР как «начальник управления по сервисному обслуживанию».
    Теперь: если под именем должности нет (сразу телефон, почта или следующий человек), она
    берётся из ближайшей строки СВЕРХУ — при условии, что та не ФИО и не телефон.

    ЗАГОЛОВОК ПОДРАЗДЕЛЕНИЯ ЖИВЁТ НЕДОЛГО. На той же странице «Служба главного инженера» —
    пункт бокового МЕНЮ, а не заголовок раздела, и он приписался всем людям страницы. Меню
    выглядит как заголовки: десяток коротких строк подряд, «Отдел продаж», «Закупки и
    логистика», «Инженерный центр». Отличить его от настоящего заголовка по виду строки
    нельзя — зато видно по расстоянию: настоящий заголовок стоит рядом со своими людьми.
    Поэтому заголовок действует не дальше ГРАНICA_ZAGOLOVKA непустых строк."""
    GRANICA_ZAGOLOVKA = 12
    stroki = [s.strip() for s in (tekst or '').split('\n')]
    lyudi, podrazd, zagol_na = [], '', -10 ** 6
    for i, s in enumerate(stroki):
        z = ZAGOL.match(s)
        if z and not FIO.match(s):
            podrazd = z.group(1).strip()
            zagol_na = i
            continue
        if not FIO.match(s):
            continue
        okno = [x for x in stroki[i + 1:i + 6] if x]
        dolzh, tel, poc = '', '', ''
        byl_kontakt = False
        for x in okno:
            if FIO.match(x):
                break                      # начался следующий человек — чужое не берём
            est_tel, est_poc = TEL.search(x), POCHTA.search(x)
            if not tel and est_tel:
                tel = est_tel.group(0).strip()
            if not poc and est_poc:
                poc = est_poc.group(0)
            if est_tel or est_poc:
                byl_kontakt = True
                continue
            # ДОЛЖНОСТЬ СНИЗУ ЗАСЧИТЫВАЕТСЯ ТОЛЬКО ДО ТЕЛЕФОНА. Это и есть признак, которым
            # различаются два порядка вёрстки, и различаются надёжно:
            #   Каустик:  имя → ДОЛЖНОСТЬ → телефон      (должность до контакта — наша)
            #   Кировец:  имя → телефон → почта → ДОЛЖНОСТЬ следующего → его имя
            # Без этого условия каждый получал должность соседа снизу, и «Зам. директора по
            # качеству» уезжал в технические ЛПР как «начальник управления по обслуживанию».
            if not dolzh and not byl_kontakt and DOLZH.match(x) \
                    and not NE_DOLZHNOST.match(x):
                dolzh = x
        otkuda_dolzh = 'снизу' if dolzh else ''
        if not dolzh:
            for j in range(i - 1, max(-1, i - 4), -1):
                x = stroki[j].strip()
                if not x:
                    continue
                if FIO.match(x) or TEL.search(x) or POCHTA.search(x):
                    break
                if DOLZH.match(x) and not NE_DOLZHNOST.match(x) and not ZAGOL.match(x):
                    dolzh, otkuda_dolzh = x, 'сверху'
                break
        if dolzh or tel or poc:
            blizko = (i - zagol_na) <= GRANICA_ZAGOLOVKA
            lyudi.append({'chelovek': s, 'dolzhnost': dolzh[:120], 'telefon': tel,
                          'pochta': poc, 'podrazdelenie': podrazd[:70] if blizko else '',
                          'dolzhnost_otkuda': otkuda_dolzh})
    return lyudi
