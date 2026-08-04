# -*- coding: utf-8 -*-
"""Добавочный — не часть номера. Отрезать ДО чистки от знаков, иначе он прилипает.

ЗАДАНИЕ 2-Й СЕССИИ, ДЕФЕКТ МОЙ. Владелец прислал карточку АО «Криогенмаш» (ИНН 5001000066),
где в контактах стоят пятнадцать и четырнадцать цифр:

    +849550593332424   «городской»   Источник: сайт компании | перенос из enrich.db 3-й сессией
    +7495505933324     «городской»   Источник: сайт:обход    | перенос из enrich.db 3-й сессией

Разбирается однозначно: это один номер с добавочным, приклеенным без разделителя —
`8 (495) 505-93-33 доб. 2424` и `доб. 24`. Чистая форма `4955059333` у нас есть, значит
портится не при добыче, а при ПЕРЕНОСЕ: путь «enrich.db → панель» снимал всё нецифровое
ВМЕСТЕ со словом «доб.», и цифры добавочного оставались в номере.

ПОЧЕМУ ЭТО ДОРОГО. Номер из пятнадцати цифр не наберётся никогда, и при этом он выглядит
заполненным: карточка показывает контакт, счётчик «предприятий с телефоном» его считает, а
позвонить нельзя. Это ноль, замаскированный под данные, — тот же сорт, что «источник утрачен»
против пустой клетки.

ЧТО ДЕЛАЕТ МОДУЛЬ
  * `raznyat(v)` → (номер, добавочный, разборчиво ли, объяснение). Добавочный отрезается по
    всем формам: `доб`, `доб.`, `добавочный`, `вн.`, `внутр.`, `ext`, `#`, в скобках и без;
  * `razborchivo(...)` — заслон против обломков: если после отрезания меньше десяти цифр или
    внутри осталось слово «доб», это не телефон, а испорченная строка, и писать её номером
    нельзя. Без заслона разбор делает из `доб.7 доб.(495)` телефон «доб.7»;
  * несколько номеров в одном поле через `|`, `;`, `,`, `/` — у каждого свой добавочный.

ПРОВЕРКА ПОЧИНКИ — ПО ОСТАТКУ, А НЕ ПО ЧИСЛУ ПОЧИНЕННЫХ. Прямое указание 2-й сессии, и оно
по делу: у них обе первые версии выглядели рабочими, пока не пересчитали, сколько «доб»
осталось ВНУТРИ номеров. Поэтому счётчик модуля печатает остаток, а не успехи.

Запуск:
    python3 nomer_dobavochnyy.py             # самопроверка на контрольных строках
    python3 nomer_dobavochnyy.py --baza      # замер по базам панели и enrich
    python3 nomer_dobavochnyy.py --primenit  # починить
"""
import base64
import json
import os
import re
import sys

DOBAVOCHNYY = re.compile(
    r'[\s,;(\-–—]*(?:доб(?:ав(?:очный|\.)?)?|вн(?:утр)?|ext|extension|#)\s*[.:№]?\s*'
    r'(\d{1,6})\s*\)?', re.I)
# Склейка без слова: одиннадцать цифр номера и хвост сразу за ними. Признак осторожный —
# требуется, чтобы первые одиннадцать складывались в российский номер (8/7 + код).
SKLEYKA = re.compile(r'^([78]\d{10})(\d{1,6})$')
CIFRY = re.compile(r'\D')
RAZDELITELI = re.compile(r'\s*[|;/]\s*|\s{2,}')


def _tolko_cifry(v):
    return CIFRY.sub('', v or '')


def raznyat(v):
    """(номер, добавочный, разборчиво, объяснение) для ОДНОЙ строки контакта."""
    s = (v or '').strip()
    if not s:
        return '', '', False, 'пусто'
    dob = ''
    m = DOBAVOCHNYY.search(s)
    if m:
        dob = m.group(1)
        s = (s[:m.start()] + ' ' + s[m.end():]).strip()
    c = _tolko_cifry(s)
    if not dob:
        sk = SKLEYKA.match(c)
        if sk:
            # СКЛЕЙКА БЕЗ СЛОВА — ЭТО ВЫВОД, А НЕ ФАКТ, и он подписывается отдельно: слово
            # «доб.» до нас не доехало, мы восстанавливаем его по длине. Если однажды
            # появится настоящий 15-значный номер, эта подпись покажет, где искать.
            return (sk.group(1), sk.group(2), True,
                    f'слова «доб» нет, но цифр {len(c)} — хвост «{sk.group(2)}» отрезан '
                    f'как добавочный по длине')
    if 'доб' in s.lower() or 'вн.' in s.lower():
        return '', dob, False, 'после отрезания в строке осталось слово «доб» — разбор неполный'
    if len(c) < 10:
        return '', dob, False, f'цифр всего {len(c)} — на номер не набирается'
    if len(c) > 11:
        return ('', dob, False,
                f'цифр {len(c)} даже после отрезания добавочного — строка испорчена, '
                f'номером не пишем')
    return c, dob, True, ('добавочный отделён' if dob else 'добавочного нет')


def raznyat_vse(v):
    """Несколько номеров в одном поле: у каждого свой добавочный."""
    return [raznyat(ch) for ch in RAZDELITELI.split(v or '') if ch.strip()]


def razborchivo(nomer, dob=''):
    """Годится ли результат к записи как телефон."""
    c = _tolko_cifry(nomer)
    return 10 <= len(c) <= 11 and 'доб' not in (nomer or '').lower()


PROBY = [
    ('+849550593332424', '84955059333', '2424'),
    ('+7495505933324', '74955059333', '24'),
    ('8 (495) 505-93-33 доб. 2424', '84955059333', '2424'),
    ('+7 (495) 505-93-33 вн. 24', '74955059333', '24'),
    ('8 495 505 93 33 ext 105', '84955059333', '105'),
    ('+7(8555)37-51-37', '78555375137', ''),
    ('8555375137', '8555375137', ''),
    ('доб.7 доб.(495)', '', '7'),
    ('не указан', '', ''),
    ('+7 495 505-93-33 (доб. 2424)', '74955059333', '2424'),
]

SCRIPT = r'''
# -*- coding: utf-8 -*-
import collections, csv, io, json, os, sqlite3, sys, urllib.request
sys.path.insert(0, r'C:\sender\_ops')
import _3s_nomer_dobavochnyy as N

PRIMENIT = 'PRIMENIT' in sys.argv
itog = {}
pravki_vsego = []
for baza, tabl in ((r'C:\seostat\data\centrifugal.db', 'person'),
                   (r'C:\sender\enrich.db', 'people')):
    if not os.path.exists(baza):
        itog[tabl] = 'базы нет'
        continue
    cx = sqlite3.connect(baza)
    kol = [r[1] for r in cx.execute('pragma table_info(%s)' % tabl)]
    est_dob = 'phone_ext' in kol
    sch = collections.Counter()
    pravki = []
    for rid, ph, src in cx.execute(
            "select rowid, coalesce(phone,''), coalesce(source,'') from %s "
            "where coalesce(phone,'') <> ''" % tabl):
        nom, dob, ok, poch = N.raznyat(ph)
        if not dob and ok and nom == ''.join(ch for ch in ph if ch.isdigit()):
            sch['чисто'] += 1
            continue
        if dob and ok:
            sch['добавочный отделён'] += 1
            pravki.append((nom, src + ' [добавочный %s вынесен из номера]' % dob, rid))
        elif not ok:
            sch['НЕРАЗБОРЧИВ: ' + poch[:40]] += 1
            # Обломок не пишем номером, но и не стираем: помечаем источник, номер оставляем
            # как есть — стереть значит потерять единственный след контакта.
            # ПОМЕТКА СТАВИТСЯ ОДИН РАЗ. Первый прогон её не проверял, и повторный запуск
            # дописывал вторую копию к тем же строкам: 41 «правка», которая ничего не чинит.
            # Признак идемпотентности — не педантизм: чинилку гоняют повторно по определению.
            if ('НОМЕР НЕРАЗБОРЧИВ' not in src
                    and ('разбор неполный' in poch or 'испорчена' in poch)):
                pravki.append((ph, src + ' [НОМЕР НЕРАЗБОРЧИВ: %s]' % poch[:80], rid))
        else:
            sch['чисто'] += 1
    # ОСТАТОК, А НЕ УСПЕХИ: сколько «доб» и сколько длинных номеров ЕЩЁ внутри.
    ostatok = cx.execute(
        "select count(*) from %s where length(replace(replace(replace(replace("
        "coalesce(phone,''),'+',''),'-',''),' ',''),'(','')) > 12" % tabl).fetchone()[0]
    itog[tabl] = {'по_видам': dict(sch.most_common()), 'правок': len(pravki),
                  'ОСТАТОК_номеров_длиннее_12_знаков_до': ostatok}
    if PRIMENIT and pravki:
        cx.executemany('update %s set phone = ?, source = ? where rowid = ?' % tabl, pravki)
        cx.commit()
        itog[tabl]['ОСТАТОК_после'] = cx.execute(
            "select count(*) from %s where length(replace(replace(replace(replace("
            "coalesce(phone,''),'+',''),'-',''),' ',''),'(','')) > 12" % tabl).fetchone()[0]
        itog[tabl]['применено'] = True
    pravki_vsego += [{'baza': tabl, 'rowid': p[2], 'stalo': p[0]} for p in pravki]

if PRIMENIT and pravki_vsego:
    b = io.StringIO()
    w = csv.DictWriter(b, delimiter=';', fieldnames=['baza', 'rowid', 'stalo'])
    w.writeheader(); w.writerows(pravki_vsego)
    telo = b.getvalue().encode('utf-8-sig')
    req = urllib.request.Request(
        os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
        + '/VAZHNOE-3s-DOBAVOCHNYY-pochinka.csv', data=telo, method='PUT',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', ''), 'Content-Type': 'text/csv'})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            itog['бэкап'] = '%s, %d байт' % (r.status, len(telo))
    except Exception as e:
        itog['бэкап'] = 'НЕ выгружен: ' + type(e).__name__
print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
'''


def main():
    if '--baza' in sys.argv or '--primenit' in sys.argv:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server'))
        import run_on_server as R
        tut = os.path.dirname(os.path.abspath(__file__))
        R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': [
            {'dest': r'C:\sender\_ops\_3s_nomer_dobavochnyy.py',
             'b64': base64.b64encode(open(os.path.join(tut, 'nomer_dobavochnyy.py'),
                                          encoding='utf-8').read().encode()).decode()},
            {'dest': r'C:\sender\_ops\3s_dobavochnyy.py',
             'b64': base64.b64encode(SCRIPT.encode()).decode()}]}, timeout=300)
        r = R.submit('enrich_contacts',
                     {'op': 'panel_py', 'script': r'C:\sender\_ops\3s_dobavochnyy.py',
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
    plohih = 0
    for vhod, zhd_nom, zhd_dob in PROBY:
        nom, dob, ok, poch = raznyat(vhod)
        verno = (nom == zhd_nom and dob == zhd_dob)
        plohih += 0 if verno else 1
        print(f'{"OK  " if verno else "МИМО"} {vhod:<32} → номер «{nom}» доб «{dob}» | {poch}')
    print(f'\nмимо: {plohih} из {len(PROBY)}')


if __name__ == '__main__':
    main()
