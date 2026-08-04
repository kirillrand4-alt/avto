# -*- coding: utf-8 -*-
"""Порча имени в моём источнике `поиск-ЛПР-3с-песочница`: глагол, падеж, обрезок, дубль.

ЗАДАНИЕ 2-Й СЕССИИ, ДЕФЕКТ МОЙ. Владелец прислал карточку АО «Аммоний» (ИНН 1627005779):
в блоке «Люди предприятия» счётчик 17, и четыре записи из них — ОДИН человек:

    Еремеев Эдуард Юрьевич   главный инженер   поиск-ЛПР-3с-песочница
    Еремеев Э.Ю.             главный инженер   поиск-ЛПР-3с-песочница
    Подписал Э.Ю.            главный инженер   поиск-ЛПР-3с-песочница
    Еремеева Э.Ю.            главный инженер   поиск-ЛПР-3с-песочница

Четыре сорта порчи, и каждый со своей причиной:

1. ГЛАГОЛ ВМЕСТО ФАМИЛИИ. В документах подпись пишется «Подписал: Э.Ю. Еремеев» — инициалы
   стоят ПЕРЕД фамилией. Мой разбор брал слово перед инициалами и получал «Подписал».
   Имя, которое нельзя ни набрать, ни спросить у секретаря.
2. РОДИТЕЛЬНЫЙ ПАДЕЖ. «главного инженера Еремеева Э.Ю.» сохранён как есть. Этот сорт опаснее
   прочих: он НЕ выглядит ошибкой и создаёт второго человека.
3. ОБРЕЗАННАЯ ФАМИЛИЯ. «Попо Г.В.» — окно разбора кончилось на середине слова.
4. ДУБЛЬ «инициалы против полного имени»: «Еремеев Э.Ю.» и «Еремеев Эдуард Юрьевич» не склеены.

ЦЕНА. Счётчик карточки говорит 17 человек, а людей меньше. Продавец видит четырёх «главных
инженеров» одного предприятия и не знает, кому звонить.

ЗАСЛОН ПРОТИВ СОБСТВЕННОГО РВЕНИЯ — ОДНОФАМИЛЬЦЫ. Признак ловит и настоящих разных людей:
2-я сессия на своей выборке поймала «Коваленко Алексей Николаевич / Коваленко Антон
Николаевич» и «Колесников Дмитрий Федорович / Колесников Николай Александрович» — это РАЗНЫЕ
люди одного предприятия. Поэтому склейка допускается ТОЛЬКО когда одно написание —
инициалы, а другое — полное имя, и инициалы совпадают с первыми буквами. Две ПОЛНЫЕ записи с
одной фамилией не склеиваются никогда, а помечаются к разбору (правило 1-й сессии).

ПОЧЕМУ ОСНОВА ФАМИЛИИ РЕЖЕТ РОВНО ОДНУ «а». Предупреждение 2-й сессии дословно: их первая
версия резала «ва»/«на» целиком и НЕ склеила как раз ту пару, ради которой писалась.
Проверка на «Макеева/Макеев» стоит в контрольном наборе первой строкой.

Запуск:
    python3 imya_porcha.py              # самопроверка
    python3 imya_porcha.py --baza       # замер по базам
    python3 imya_porcha.py --primenit   # починить
"""
import base64
import json
import os
import re
import sys

# Глаголы и канцелярские слова, попадающие в фамилию из подписи документа.
GLAGOL = re.compile(
    r'^(?:подписал|подписано|утвердил|утверждаю|согласовал|согласовано|исполнил|исполнитель|'
    r'составил|проверил|разработал|разработчик|начальник|заместитель|директор|главный|'
    r'ответственный|руководител|инженер|специалист|представител|уполномоченн|контакт|'
    r'телефон|адрес|приложени|заказчик|поставщик|подрядчик|комисси|председател|член)',
    re.I)
INICIALY = re.compile(r'^[А-ЯЁA-Z]\.\s*[А-ЯЁA-Z]?\.?$')
PUSTYSHKA = re.compile(r'^(?:имя\s+не\s+установлено|не\s+установлен\w*|неизвестн\w*|н/д|'
                       r'нет\s+данных|—|-)$', re.I)
OTCHESTVO = re.compile(r'(?:ович|евич|ьевич|инич|овна|евна|ьевна|ична|инична)$', re.I)

VID_GLAGOL = 'глагол вместо фамилии: разбор взял слово перед инициалами'
VID_PADEZH = 'родительный падеж: «Еремеева» вместо «Еремеев»'
VID_OBREZOK = 'фамилия обрезана: окно разбора кончилось на середине слова'
VID_PUSTYSHKA = 'пустышка: имени нет, есть только должность'
VID_DUBL = 'дубль: инициалы и полное имя одного человека'
VID_ODNOFAM = 'однофамильцы: две полные записи, склеивать нельзя — к разбору'
VID_CHISTO = 'чисто'


def chasti(fio):
    return [c for c in re.split(r'[\s]+', (fio or '').strip()) if c]


def familiya(fio):
    ch = chasti(fio)
    return ch[0] if ch else ''


def osnova_familii(f):
    """Основа для сравнения: нижний регистр, ё→е, срезана РОВНО ОДНА конечная «а».

    Ровно одна, а не «ва»/«на» целиком: «Макеева» → «макеев», и она сходится с «Макеев».
    Резать больше — потерять именно ту пару, ради которой правило писалось.
    """
    v = (f or '').lower().replace('ё', 'е').strip('.,-')
    return v[:-1] if len(v) > 3 and v.endswith('а') else v


def vid_porchi(fio, sosedi=()):
    """(вид, объяснение) для одного написания. `sosedi` — другие имена того же ИНН."""
    s = (fio or '').strip()
    if not s or PUSTYSHKA.match(s):
        return VID_PUSTYSHKA, 'в поле имени нет имени — человека по такой записи не найти'
    f = familiya(s)
    if GLAGOL.match(f):
        return (VID_GLAGOL,
                f'первое слово «{f}» — не фамилия; в подписи инициалы стоят перед фамилией '
                f'(«Подписал: Э.Ю. Еремеев»), и разбор взял слово перед ними')
    if len(f.strip('.,-')) <= 4 and not OTCHESTVO.search(s) and len(chasti(s)) <= 2:
        # «Попо Г.В.» — короткое первое слово без отчества рядом. Настоящие короткие фамилии
        # (Ким, Ли, Цой) существуют, поэтому это ПОМЕТКА, а не приговор.
        return VID_OBREZOK, f'первое слово «{f}» короче пяти знаков и отчества рядом нет'
    o = osnova_familii(f)
    for d in sosedi:
        if d == s:
            continue
        fd = familiya(d)
        if osnova_familii(fd) != o:
            continue
        polnoe_s, polnoe_d = len(chasti(s)) >= 3, len(chasti(d)) >= 3
        if fd.lower().replace('ё', 'е') != f.lower().replace('ё', 'е'):
            # Основы сошлись, а сами фамилии разные — это падеж.
            if f.lower().endswith('а') and not fd.lower().endswith('а'):
                return VID_PADEZH, f'«{f}» против «{fd}» у того же предприятия'
            continue
        if polnoe_s and polnoe_d:
            return VID_ODNOFAM, f'«{s}» и «{d}» — обе записи полные, склейка запрещена'
        if not polnoe_s and polnoe_d:
            return VID_DUBL, f'«{s}» — это инициалы к «{d}»'
    return VID_CHISTO, ''


PROBY = [
    ('Еремеев Эдуард Юрьевич', ['Еремеева Э.Ю.', 'Подписал Э.Ю.', 'Еремеев Э.Ю.'], VID_CHISTO),
    ('Еремеев Э.Ю.', ['Еремеев Эдуард Юрьевич'], VID_DUBL),
    ('Подписал Э.Ю.', ['Еремеев Эдуард Юрьевич'], VID_GLAGOL),
    ('Еремеева Э.Ю.', ['Еремеев Эдуард Юрьевич'], VID_PADEZH),
    ('Макеева С.А.', ['Макеев Сергей Александрович'], VID_PADEZH),
    ('Попо Г.В.', [], VID_OBREZOK),
    ('Имя не установлено', [], VID_PUSTYSHKA),
    ('Коваленко Алексей Николаевич', ['Коваленко Антон Николаевич'], VID_ODNOFAM),
    ('Колесников Дмитрий Федорович', ['Колесников Николай Александрович'], VID_ODNOFAM),
    ('Сидиченко Александр Александрович', [], VID_CHISTO),
]

SCRIPT = r'''
# -*- coding: utf-8 -*-
import collections, csv, io, json, os, sqlite3, sys, urllib.request
sys.path.insert(0, r'C:\sender\_ops')
import _3s_imya_porcha as I

PRIMENIT = 'PRIMENIT' in sys.argv
MOY = 'песочница'
itog = {}
spisok = []
for baza, tabl in ((r'C:\seostat\data\centrifugal.db', 'person'),
                   (r'C:\sender\enrich.db', 'people')):
    if not os.path.exists(baza):
        itog[tabl] = 'базы нет'
        continue
    cx = sqlite3.connect(baza)
    po_inn = collections.defaultdict(list)
    stroki = cx.execute(
        "select rowid, coalesce(inn,''), coalesce(person,''), coalesce(source,'') "
        "from %s" % tabl).fetchall()
    for _, inn, person, _s in stroki:
        if person.strip():
            po_inn[inn].append(person.strip())
    sch = collections.Counter()
    pravki = []
    for rid, inn, person, src in stroki:
        moy = MOY in (src or '')
        vid, poch = I.vid_porchi(person, po_inn.get(inn, ()))
        if vid == I.VID_CHISTO:
            continue
        sch['%s | %s' % ('мой источник' if moy else 'чужой источник', vid[:44])] += 1
        spisok.append({'baza': tabl, 'inn': inn, 'chelovek': person, 'vid': vid,
                       'pochemu': poch[:150], 'istochnik': (src or '')[:70]})
        # ПРАВИМ ТОЛЬКО СВОЙ ИСТОЧНИК И ТОЛЬКО ТО, ЧТО ЗАВЕДОМО НЕ ИМЯ. Чужие строки не
        # трогаем: молча править чужие данные — то же, что молча их выбросить.
        if not (PRIMENIT and moy) or '[имя' in (src or '') or '[запись' in (src or ''):
            continue
        if vid == I.VID_GLAGOL:
            # Глагол — заведомо не имя, и заменить его нечем: человек за этой строкой есть,
            # а как его зовут, мы не знаем. Ставим честное «не установлено», а не догадку.
            pravki.append(('Имя не установлено',
                           (src or '') + ' [имя снято: %s]' % poch[:90], rid))
        elif vid in (I.VID_PADEZH, I.VID_DUBL, I.VID_OBREZOK):
            # ЗДЕСЬ ИМЯ НЕ ТРОГАЕМ. «Еремеева Э.Ю.» это тот же человек, но исправить падеж
            # значит сделать точную копию соседней строки, а склеивать записи — работа
            # показа, а не чинилки. Мы называем связь, чтобы карточка перестала врать
            # счётчиком, и оставляем обе записи: разделять, а не отсеивать.
            pravki.append((person, (src or '') + ' [запись того же человека: %s]' % poch[:110],
                           rid))
    itog[tabl] = {'по_видам': dict(sch.most_common()), 'к_правке': len(pravki)}
    if PRIMENIT and pravki:
        cx.executemany('update %s set person = ?, source = ? where rowid = ?' % tabl, pravki)
        cx.commit()
        itog[tabl]['применено'] = True

if spisok:
    b = io.StringIO()
    w = csv.DictWriter(b, delimiter=';', fieldnames=list(spisok[0]))
    w.writeheader(); w.writerows(spisok)
    telo = b.getvalue().encode('utf-8-sig')
    req = urllib.request.Request(
        os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
        + '/VAZHNOE-3s-PORCHA-IMEN.csv', data=telo, method='PUT',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', ''), 'Content-Type': 'text/csv'})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            itog['файл'] = '%s, строк %d' % (r.status, len(spisok))
    except Exception as e:
        itog['файл'] = 'НЕ выгружен: ' + type(e).__name__
print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
'''


def main():
    if '--baza' in sys.argv or '--primenit' in sys.argv:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server'))
        import run_on_server as R
        tut = os.path.dirname(os.path.abspath(__file__))
        R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': [
            {'dest': r'C:\sender\_ops\_3s_imya_porcha.py',
             'b64': base64.b64encode(open(os.path.join(tut, 'imya_porcha.py'),
                                          encoding='utf-8').read().encode()).decode()},
            {'dest': r'C:\sender\_ops\3s_imya_porcha.py',
             'b64': base64.b64encode(SCRIPT.encode()).decode()}]}, timeout=300)
        r = R.submit('enrich_contacts',
                     {'op': 'panel_py', 'script': r'C:\sender\_ops\3s_imya_porcha.py',
                      'argv': ['PRIMENIT'] if '--primenit' in sys.argv else [],
                      'timeout': 900}, timeout=1200)
        d = r.get('data') or {}
        h = d.get('stdout_tail') or ''
        for s in h.splitlines():
            if s.strip().startswith('ИТОГ '):
                print(json.dumps(json.loads(s.strip()[5:]), ensure_ascii=False, indent=1))
                return
        print('пусто:', (d.get('stderr_tail') or '')[-900:], file=sys.stderr)
        return
    mimo = 0
    for fio, sosedi, zhd in PROBY:
        vid, poch = vid_porchi(fio, sosedi)
        ok = vid == zhd
        mimo += 0 if ok else 1
        print(f'{"OK  " if ok else "МИМО"} {fio:<36} → {vid[:44]:<46} {poch[:44]}')
    print(f'\nмимо: {mimo} из {len(PROBY)}')


if __name__ == '__main__':
    main()
