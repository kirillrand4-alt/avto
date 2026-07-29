# -*- coding: utf-8 -*-
"""Утверждение №1, часть 2: где именно теряется разбор ФИО (email_schema)."""
import glob
import importlib.util
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
import enrich_db as EDB  # noqa: E402

пути = glob.glob(r'C:\sender\_ops\*email_schema*.py') + \
    glob.glob(r'C:\sender\server\ops\*email_schema*.py')
sys.argv = [sys.argv[0]]
spec = importlib.util.spec_from_file_location('es_mod', пути[0])
ES = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ES)

db = EDB.EnrichDB()
e = db.cx
out = {'модуль': пути[0]}

# ---------- A. ТОЧНО КОДОМ АВТОРА: сколько компаний дают правило ----------
цели = [r[0] for r in e.execute(
    'select distinct inn from people where person<>"" '
    'and (email is null or email="")')]
дал_правило, один_голос, ноль = [], 0, 0
нет_домена = 0
for inn in цели:
    дом = ES.свой_домен(inn)
    if not дом or дом in ES._ПУБЛИЧНЫЕ:
        нет_домена += 1
        continue
    имя, n, прим = ES.вывести_схему(inn, дом)
    if имя:
        дал_правило.append({'инн': inn, 'дом': дом, 'правило': имя,
                            'голосов': n, 'адреса': прим[:3]})
    elif n:
        один_голос += 1
    else:
        ноль += 1
out['A_воронка_кодом_автора'] = {
    'целей': len(цели), 'без_своего_домена': нет_домена,
    'правило_выведено': len(дал_правило), 'один_голос': один_голос,
    'ни_одного_голоса': ноль, 'кто': дал_правило}

# двойной счёт: один и тот же адрес лежит и в emails, и в people
дубль = e.execute(
    'select count(*) from emails em join people p on p.inn=em.inn '
    'and lower(p.email)=lower(em.email) where em.person<>"" and p.person<>""'
).fetchone()[0]
out['A_адресов_дублируется_emails_и_people'] = дубль

# ---------- Б. КЛАССИФИКАЦИЯ НЕУЗНАННЫХ ПАР ----------
пары = [((a or '').lower().strip(), p or '') for a, p in e.execute(
    'select email, person from emails where person<>"" and email like "%@%"')]


def фам_варианты(фио):
    """Все транслиты ВСЕХ слов ФИО длиной 4+ (порядок слов не важен)."""
    сл = [x for x in re.split(r'[\s.,()]+', фио) if len(x) > 3]
    из = set()
    for с in сл:
        for v in ES.варианты(с):
            if len(v) > 3:
                из.add(v)
    return из


рол = re.compile(r'^(info|mail|office|sales?|zakaz|order|opt|shop|buh|account|'
                 r'hr|job|rabota|support|help|admin|secretar|priemn|reception|'
                 r'director|dir|komdir|gendir|ceo|rop|manager|zam|snab|logist|'
                 r'sklad|tender|zakup|market|pr|reklama|assist|tech|service|'
                 r'servis|post|kadr|ok|otdel|trade|b2b|opt)[0-9_.\-]*$')
кл = {'узнан': 0, 'НЕузнан_имя_в_адресе': 0, 'НЕузнан_ролевой': 0,
      'НЕузнан_прочее': 0}
потери = []
for a, p in пары:
    лок = a.split('@')[0]
    if ES.кандидаты(p).get(лок):
        кл['узнан'] += 1
        continue
    if рол.match(лок):
        кл['НЕузнан_ролевой'] += 1
        continue
    вар = фам_варианты(p)
    if any(v in лок or лок in v for v in вар):
        кл['НЕузнан_имя_в_адресе'] += 1
        if len(потери) < 45:
            потери.append({'локальная': лок, 'фио': p})
    else:
        кл['НЕузнан_прочее'] += 1
out['Б_классификация_2131_пары'] = кл
out['Б_ПОТЕРИ_имя_есть_а_правило_не_вывелось'] = потери

# ---------- В. ИМЕННЫЕ ПРОВЕРКИ НАПИСАНИЙ ----------
тесты = [
    ('Фёдоров Иван Петрович', 'fedorov'), ('Фёдоров Иван Петрович', 'fyodorov'),
    ('Фёдоров Иван Петрович', 'i.fedorov'),
    ('Иванов-Петров Сергей Ильич', 'ivanov-petrov'),
    ('Иванов-Петров Сергей Ильич', 'ivanovpetrov'),
    ('Иванов-Петров Сергей Ильич', 'petrov'),
    ('Сергей Ильич Иванов', 'ivanov'),
    ('Арсентьева Мария Ильинична', 'arsentyeva'),
    ('Арсентьева Мария Ильинична', 'arsenteva'),
    ('Дьяченко Пётр Кузьмич', 'dyachenko'),
    ('Ильин Сергей Ильич', 'ilyin'),
    ('Владимир Ермак', 'ermak'), ('Артур Кравцов', 'kravtsov'),
    ('Ольга Бибишева', 'o.bibisheva'),
    ('Бойко', 'boyko'), ('Бойко', 'boykoaa'),
    ('Хижняк Сергей Иванович', 'hsi'),
    ('Хижняк Сергей Иванович', 'khizhnyak'),
    ('Хижняк Сергей Иванович', 's.khizhnyak'),
    ('Евгения Хваткова (отдел кадров)', 'ev.hvatkova'),
    ('ОСЬКИН КОНСТАНТИН ВЛАДИМИРОВИЧ', 'oskin'),
    ('Оськин К.В.', 'k.oskin'), ('Оськин К.В.', 'oskin.kv'),
    ('Щукин Юрий Яковлевич', 'schukin'), ('Щукин Юрий Яковлевич', 'shchukin'),
    ('Цой Александр Ким', 'coy'), ('Цой Александр Ким', 'tsoy'),
    ('Гаджиев Магомед Гаджи оглы', 'gadzhiev'),
    ('Ким Ольга Ивановна', 'kim'), ('Ким Ольга Ивановна', 'o.kim'),
    ('Соловьёв Александр Юрьевич', 'solovyev'),
    ('Соловьёв Александр Юрьевич', 'soloviev'),
    ('Соловьёв Александр Юрьевич', 'solovev'),
]
out['В_проверка_написаний'] = [
    {'фио': ф, 'локальная': л, 'узнан': ES.кандидаты(ф).get(л) or 'НЕТ'}
    for ф, л in тесты]

# ---------- Г. 10 РЕАЛЬНЫХ ПАР С ФАМИЛИЕЙ В АДРЕСЕ ----------
взято = []
for a, p in пары:
    лок = a.split('@')[0]
    if рол.match(лок) or len(p.split()) < 2:
        continue
    вар = фам_варианты(p)
    if not any(v in лок for v in вар):
        continue
    взято.append({'адрес': a, 'фио': p,
                  'правило': ES.кандидаты(p).get(лок) or 'НЕ РАСПОЗНАН',
                  'части': ES.части(p)})
    if len(взято) >= 10:
        break
out['Г_10_реальных_пар'] = взято

print(json.dumps(out, ensure_ascii=False, indent=1)[:16000])
print('ИТОГ ' + json.dumps({'A': {k: v for k, v in out['A_воронка_кодом_автора'].items()
                                 if k != 'кто'}, 'дубль': дубль, 'Б': кл},
                           ensure_ascii=False))
