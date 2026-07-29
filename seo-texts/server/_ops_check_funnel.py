# -*- coding: utf-8 -*-
"""Адверсариальная перепроверка утверждения №1: воронка схемы корпоративной почты."""
import glob
import importlib.util
import json
import os
import sys

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
import enrich_db as EDB      # noqa: E402
import enrich_contacts as EC  # noqa: E402

out = {}

# --- найти и загрузить модуль email_schema КАК ОН РАЗВЁРНУТ НА СЕРВЕРЕ ---
кандидаты_путей = glob.glob(r'C:\sender\_ops\*email_schema*.py') + \
    glob.glob(r'C:\sender\server\*email_schema*.py') + \
    glob.glob(r'C:\sender\server\ops\*email_schema*.py')
out['найденные_файлы_email_schema'] = кандидаты_путей
out['листинг_ops'] = sorted(os.path.basename(p)
                            for p in glob.glob(r'C:\sender\_ops\*.py'))[:80]
ES = None
if кандидаты_путей:
    sys.argv = [sys.argv[0]]      # чтобы модуль не подхватил --apply
    spec = importlib.util.spec_from_file_location('es_mod', кандидаты_путей[0])
    ES = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ES)
out['ES_загружен'] = bool(ES)

db = EDB.EnrichDB()
e = db.cx

# ---------- ВОРОНКА ----------
out['people_всего'] = e.execute('select count(*) from people').fetchone()[0]
out['людей_с_фио_без_почты'] = e.execute(
    'select count(*) from people where person<>"" and (email is null or email="")'
).fetchone()[0]
цели = [r[0] for r in e.execute(
    'select distinct inn from people where person<>"" '
    'and (email is null or email="")')]
out['компаний_с_безадресными'] = len(цели)

_ПУБ = getattr(ES, '_ПУБЛИЧНЫЕ', None) or {
    'mail.ru', 'yandex.ru', 'ya.ru', 'gmail.com', 'bk.ru', 'inbox.ru',
    'list.ru', 'rambler.ru', 'internet.ru', 'yahoo.com', 'icloud.com'}

сайты = {r[0]: (r[1] or '') for r in e.execute('select inn, site from companies')}
# все адреса по компаниям (для альтернативного источника домена)
адреса = {}
for inn, em, pers in e.execute(
        'select inn, email, person from emails where email like "%@%"'):
    адреса.setdefault(inn, []).append(((em or '').lower().strip(), pers or ''))
for inn, em, pers in e.execute(
        'select inn, email, person from people where email like "%@%"'):
    адреса.setdefault(inn, []).append(((em or '').lower().strip(), pers or ''))

ст = {'нет_сайта': 0, 'сайт_публичный': 0, 'свой_домен': 0}
без_сайта_но_есть_корп_домен = 0
адр_на_домене = {'0': 0, '1': 0, '2+': 0}          # адресов с ФИО на своём домене
адр_любых = {'0': 0, '1': 0, '2+': 0}              # адресов ЛЮБЫХ на своём домене
распознано = {'ни_один': 0, 'один': 0, 'два+': 0}
непонятые = []          # (адрес, фио) на своём домене, где правило не выведено
понятые = []
схемы_голоса = {}
for inn in цели:
    дом = (EC.site_domain(сайты.get(inn, '')) or '').lower()
    if not дом:
        ст['нет_сайта'] += 1
        корп = {a.split('@')[1] for a, _ in адреса.get(inn, [])
                if '@' in a and a.split('@')[1] not in _ПУБ}
        if корп:
            без_сайта_но_есть_корп_домен += 1
        continue
    if дом in _ПУБ:
        ст['сайт_публичный'] += 1
        continue
    ст['свой_домен'] += 1
    свои = [(a, p) for a, p in адреса.get(inn, []) if a.endswith('@' + дом)]
    k = len(свои)
    адр_любых['0' if k == 0 else ('1' if k == 1 else '2+')] += 1
    сфио = [(a, p) for a, p in свои if (p or '').strip()]
    k2 = len(сфио)
    адр_на_домене['0' if k2 == 0 else ('1' if k2 == 1 else '2+')] += 1
    if not ES:
        continue
    голоса = {}
    for a, p in сфио:
        лок = a.split('@')[0]
        имя = ES.кандидаты(p).get(лок)
        if имя:
            голоса[имя] = голоса.get(имя, 0) + 1
            if len(понятые) < 12:
                понятые.append({'адрес': a, 'фио': p, 'правило': имя})
        else:
            if len(непонятые) < 60:
                непонятые.append({'адрес': a, 'фио': p, 'инн': inn})
    n = max(голоса.values()) if голоса else 0
    распознано['ни_один' if n == 0 else ('один' if n == 1 else 'два+')] += 1
    for имя, v in голоса.items():
        схемы_голоса[имя] = схемы_голоса.get(имя, 0) + v

out['домен_компаний_целей'] = ст
out['без_сайта_но_есть_корп_домен_в_адресах'] = без_сайта_но_есть_корп_домен
out['адресов_ЛЮБЫХ_на_своём_домене'] = адр_любых
out['адресов_С_ФИО_на_своём_домене'] = адр_на_домене
out['схема_по_голосам'] = распознано
out['голоса_по_правилам'] = схемы_голоса
out['примеры_ПОНЯТЫХ'] = понятые
out['примеры_НЕПОНЯТЫХ_на_своём_домене'] = непонятые[:25]

# ---------- 2. ОБЩИЙ ЗАМЕР РАЗБОРА ФИО: все пары адрес+ФИО в emails ----------
пары = [(a, p) for a, p in e.execute(
    'select email, person from emails where person<>"" and email like "%@%"')]
out['пар_адрес_ФИО_в_emails'] = len(пары)
если = {'узнан': 0, 'не_узнан': 0}
не_узнаны = []
if ES:
    for a, p in пары:
        a = (a or '').lower().strip()
        лок = a.split('@')[0]
        if ES.кандидаты(p or '').get(лок):
            если['узнан'] += 1
        else:
            если['не_узнан'] += 1
            if len(не_узнаны) < 40:
                не_узнаны.append({'локальная': лок, 'фио': p})
out['разбор_всех_пар'] = если
out['примеры_НЕузнанных_пар'] = не_узнаны

print(json.dumps(out, ensure_ascii=False, indent=1)[:14000])
print('ИТОГ ' + json.dumps({'цели': len(цели), 'домен': ст,
                            'адр_с_фио': адр_на_домене, 'схема': распознано,
                            'пары': len(пары), 'разбор': если,
                            'без_сайта_корп': без_сайта_но_есть_корп_домен},
                           ensure_ascii=False))
