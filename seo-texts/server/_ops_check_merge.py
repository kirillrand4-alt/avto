# -*- coding: utf-8 -*-
"""Утверждение №2: сшивка «Фамилия И.О.» + полное ФИО. Насколько правило строго."""
import glob
import importlib.util
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
import enrich_db as EDB  # noqa: E402

sys.argv = [sys.argv[0]]
пути = glob.glob(r'C:\sender\_ops\*email_schema*.py') + \
    glob.glob(r'C:\sender\server\ops\*email_schema*.py')
spec = importlib.util.spec_from_file_location('es_mod', пути[0])
ES = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ES)

db = EDB.EnrichDB()
e = db.cx
out = {}

# ---- добор по утверждению 1: чьи компании дали правило + потери разбора ----
цели = [r[0] for r in e.execute(
    'select distinct inn from people where person<>"" '
    'and (email is null or email="")')]
кто = []
for inn in цели:
    д = ES.свой_домен(inn)
    if not д or д in ES._ПУБЛИЧНЫЕ:
        continue
    имя, n, прим = ES.вывести_схему(inn, д)
    if имя:
        кто.append({'дом': д, 'правило': имя, 'голосов': n, 'адреса': прим[:2]})
out['1_кто_дал_правило'] = кто

тесты = [('Фёдоров Иван Петрович', 'fedorov'), ('Фёдоров Иван Петрович', 'fyodorov'),
         ('Иванов-Петров Сергей Ильич', 'ivanov-petrov'),
         ('Иванов-Петров Сергей Ильич', 'ivanovpetrov'),
         ('Иванов-Петров Сергей Ильич', 'petrov'),
         ('Сергей Ильич Иванов', 'ivanov'), ('Сергей Иванов', 'ivanov'),
         ('Арсентьева Мария Ильинична', 'arsentyeva'),
         ('Арсентьева Мария Ильинична', 'arsenteva'),
         ('Дьяченко Пётр Кузьмич', 'dyachenko'), ('Ильин Сергей Ильич', 'ilyin'),
         ('Владимир Ермак', 'ermak'), ('Артур Кравцов', 'kravtsov'),
         ('Ольга Бибишева', 'o.bibisheva'),
         ('Халин В.В.', 'khalin-vv'), ('Халин Виктор Васильевич', 'khalin-vv'),
         ('Нефёдова Я.А.', 'nefedova-ya'), ('Петров И.С.', 'petrov-is'),
         ('Петров Иван Сергеевич', 'petrov-i'), ('Петров Иван Сергеевич', 'i-petrov'),
         ('Петров Иван Сергеевич', 'ivan-petrov'),
         ('Хижняк Сергей Иванович', 'hsi'), ('Бойко', 'boyko')]
out['1_написания'] = {f'{ф} -> {л}': (ES.кандидаты(ф).get(л) or 'НЕТ')
                      for ф, л in тесты}

# ======================= УТВЕРЖДЕНИЕ 2 =======================
люди = [dict(zip(('rowid', 'inn', 'person', 'post', 'source'), r))
        for r in e.execute('select rowid, inn, person, post, source from people')]
out['2_людей_всего'] = len(люди)

_КРАТКО = re.compile(r'^([А-ЯЁ][а-яё\-]{2,})\s+([А-ЯЁ])\.\s?([А-ЯЁ])\.?$')
_ПОЛНО = re.compile(r'^([А-ЯЁ][а-яё\-]{2,})\s+([А-ЯЁ][а-яё]{1,})\s+([А-ЯЁ][а-яё]{1,})$')

# --- ослабленные формы ---
# краткая: инициалы после ИЛИ до фамилии, 1 или 2 инициала, с точками и без,
# любой регистр, мусор/должность после запятой отбрасываем
_К2 = re.compile(r'^([А-ЯЁ][А-ЯЁа-яё\-]{1,})\s*[,]?\s+([А-ЯЁ])\.?\s?([А-ЯЁ])?\.?$')
_К3 = re.compile(r'^([А-ЯЁ])\.\s?([А-ЯЁ])\.?\s*([А-ЯЁ][А-ЯЁа-яё\-]{1,})$')
_П2 = re.compile(r'^([А-ЯЁ][А-ЯЁа-яё\-]{1,})\s+([А-ЯЁ][А-ЯЁа-яё\-]{1,})'
                 r'(?:\s+([А-ЯЁ][А-ЯЁа-яё\-]{1,}))?$')
_ОТЧ = re.compile(r'(ович|евич|ьич|ич|овна|евна|ична|инична|ична)$', re.I)


def чист(s):
    s = re.sub(r'\(.*?\)', ' ', (s or '')).strip()
    s = re.sub(r'[,;].*$', '', s).strip()
    return re.sub(r'\s+', ' ', s)


def ёе(s):
    return (s or '').replace('ё', 'е').replace('Ё', 'Е').lower()


def кратко2(s):
    """(фамилия, и1, и2 или '') из любой краткой формы."""
    s = чист(s)
    m = _К2.match(s)
    if m:
        return m.group(1), m.group(2), (m.group(3) or '')
    m = _К3.match(s)
    if m:
        return m.group(3), m.group(1), m.group(2)
    return None


def полно2(s):
    """(фамилия, имя, отчество или '') — порядок определяем по отчеству."""
    s = чист(s)
    m = _П2.match(s)
    if not m:
        return None
    ч = [x for x in m.groups() if x]
    if len(ч) == 3:
        if _ОТЧ.search(ч[1]):
            ч = [ч[2], ч[0], ч[1]]
        return ч[0], ч[1], ч[2]
    if len(ч) == 2:
        if _ОТЧ.search(ч[1]):      # «Иван Петрович» — фамилии нет
            return None
        return ч[0], ч[1], ''
    return None


по_инн = {}
for s in люди:
    по_инн.setdefault(s['inn'], []).append(s)

строгих, ослабл = [], []
только_ослабл = []
формы = {'строго_кратко': 0, 'строго_полно': 0, 'ослабл_кратко': 0,
         'ослабл_полно': 0, 'ни_то_ни_то': 0}
for s in люди:
    p = (s['person'] or '').strip()
    ск, сп = bool(_КРАТКО.match(p)), bool(_ПОЛНО.match(p))
    ок, оп = bool(кратко2(p)), bool(полно2(p))
    формы['строго_кратко'] += ск
    формы['строго_полно'] += сп
    формы['ослабл_кратко'] += ок
    формы['ослабл_полно'] += оп
    if not (ок or оп):
        формы['ни_то_ни_то'] += 1
out['2_формы_записей'] = формы

for inn, гр in по_инн.items():
    кр = [(кратко2(x['person'] or ''), x) for x in гр]
    кр = [(k, x) for k, x in кр if k]
    пл = [(полно2(x['person'] or ''), x) for x in гр]
    пл = [(k, x) for k, x in пл if k]
    for (фк, и1, и2), к in кр:
        for (фп, им, от), п in пл:
            if ёе(фк) != ёе(фп):
                continue
            if ёе(им[:1]) != ёе(и1):
                continue
            if и2 and от and ёе(от[:1]) != ёе(и2):
                continue
            строг = bool(_КРАТКО.match((к['person'] or '').strip())
                         and _ПОЛНО.match((п['person'] or '').strip())
                         and _КРАТКО.match((к['person'] or '').strip()).group(1).lower()
                         == _ПОЛНО.match((п['person'] or '').strip()).group(1).lower()
                         and и2 and от and от[0] == и2 and им[0] == и1)
            зап = {'короткая': к['person'], 'полная': п['person'], 'инн': inn,
                   'должность_короткой': (к['post'] or '')[:40],
                   'строгое_правило': строг}
            ослабл.append(зап)
            if строг:
                строгих.append(зап)
            else:
                только_ослабл.append(зап)
            break
out['2_пар_строгим_правилом'] = len(строгих)
out['2_пар_ослабленным'] = len(ослабл)
out['2_добавка'] = len(только_ослабл)
out['2_примеры_добавки'] = только_ослабл[:20]

# верхняя граница: одинаковая фамилия у краткой и полной записи в одной компании
верх = 0
for inn, гр in по_инн.items():
    фк = {ёе(кратко2(x['person'] or '')[0]) for x in гр if кратко2(x['person'] or '')}
    фп = {ёе(полно2(x['person'] or '')[0]) for x in гр if полно2(x['person'] or '')}
    верх += len(фк & фп)
out['2_верхняя_граница_по_фамилии'] = верх

# сколько кратких записей вообще имеют шанс: есть ли в их компании полные
шанс = sum(1 for inn, гр in по_инн.items()
           if any(кратко2(x['person'] or '') for x in гр)
           and any(полно2(x['person'] or '') for x in гр))
out['2_компаний_где_есть_и_краткие_и_полные'] = шанс
out['2_примеры_кратких'] = [x['person'] for x in люди
                            if кратко2(x['person'] or '')][:25]

print(json.dumps(out, ensure_ascii=False, indent=1)[:15000])
print('ИТОГ ' + json.dumps({'формы': формы, 'строго': len(строгих),
                            'ослабл': len(ослабл), 'верх': верх,
                            'компаний': шанс, 'правило_дали': len(кто)},
                           ensure_ascii=False))
