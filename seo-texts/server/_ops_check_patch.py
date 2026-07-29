# -*- coding: utf-8 -*-
"""Сколько компаний дали бы правило, если закрыть найденные дыры разбора."""
import glob
import importlib.util
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
import enrich_db as EDB      # noqa: E402
import enrich_contacts as EC  # noqa: E402

sys.argv = [sys.argv[0]]
пути = glob.glob(r'C:\sender\_ops\*email_schema*.py') + \
    glob.glob(r'C:\sender\server\ops\*email_schema*.py')
spec = importlib.util.spec_from_file_location('es_mod', пути[0])
ES = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ES)

db = EDB.EnrichDB()
e = db.cx
_ОТЧ = re.compile(r'(ович|евич|ьич|ич|овна|евна|ична|инична)$', re.I)


def раскладки(фио):
    """Все правдоподобные (ф, и, о) — включая обратный порядок и однословные."""
    s = re.sub(r'\(.*?\)', ' ', фио or '')
    s = re.sub(r'[,;].*$', '', s)
    ч = [x for x in re.split(r'[\s.]+', s.strip()) if x]
    из = []
    if len(ч) == 1:
        из.append((ч[0], '', ''))
    elif len(ч) == 2:
        из.append((ч[0], ч[1], ''))
        из.append((ч[1], ч[0], ''))       # «Имя Фамилия» — вторая раскладка
    elif len(ч) >= 3:
        из.append((ч[0], ч[1], ч[2]))
        из.append((ч[2], ч[0], ч[1]))     # «Имя Отчество Фамилия»
        if _ОТЧ.search(ч[1]):
            из = [(ч[2], ч[0], ч[1]), (ч[0], ч[1], ч[2])]
    return из


def кандидаты2(фио):
    из = {}
    for ф0, и0, о0 in раскладки(фио):
        for ф in ES.варианты(ф0):
            фс = ф.replace('-', '')       # слитная двойная фамилия
            for и in (ES.варианты(и0) if и0 else {''}):
                for о in (ES.варианты(о0) if о0 else {''}):
                    и1, о1 = и[:1], о[:1]
                    п = {}
                    for фв in {ф, фс}:
                        п.update({
                            f'{и1}.{фв}': 'и.фамилия', f'{и1}{фв}': 'ифамилия',
                            f'{фв}.{и1}': 'фамилия.и', f'{фв}_{и1}': 'фамилия_и',
                            f'{фв}-{и1}': 'фамилия-и', f'{фв}{и1}': 'фамилияи',
                            фв: 'фамилия',
                            f'{и}.{фв}': 'имя.фамилия', f'{и}_{фв}': 'имя_фамилия',
                            f'{и}-{фв}': 'имя-фамилия', f'{и}{фв}': 'имяфамилия',
                            f'{фв}.{и}': 'фамилия.имя', f'{фв}-{и}': 'фамилия-имя',
                            f'{фв}_{и}': 'фамилия_имя'})
                        if о1:
                            п.update({
                                f'{фв}_{и1}{о1}': 'фамилия_ио',
                                f'{фв}.{и1}{о1}': 'фамилия.ио',
                                f'{фв}-{и1}{о1}': 'фамилия-ио',
                                f'{фв}{и1}{о1}': 'фамилияио',
                                f'{и1}{о1}{фв}': 'иофамилия',
                                f'{и1}.{о1}.{фв}': 'и.о.фамилия',
                                f'{фв[:1]}{и1}{о1}': 'фио-инициалы'})
                    for лок, имя in п.items():
                        if лок and лок not in из:
                            из[лок] = имя
    return из


цели = [r[0] for r in e.execute(
    'select distinct inn from people where person<>"" '
    'and (email is null or email="")')]
сайты = {r[0]: (r[1] or '') for r in e.execute('select inn, site from companies')}
адреса = {}
for q in ('select inn, email, person from emails where email like "%@%"',
          'select inn, email, person from people where email like "%@%"'):
    for inn, em, p in e.execute(q):
        адреса.setdefault(inn, set()).add(((em or '').lower().strip(), p or ''))

было, стало, новые = 0, 0, []
для_домена = 0
for inn in цели:
    дом = (EC.site_domain(сайты.get(inn, '')) or '').lower()
    из_адресов = ''
    if not дом:
        кор = [a.split('@')[1] for a, _ in адреса.get(inn, ())
               if '@' in a and a.split('@')[1] not in ES._ПУБЛИЧНЫЕ]
        if кор:
            из_адресов = max(set(кор), key=кор.count)
            дом = из_адресов
    if not дом or дом in ES._ПУБЛИЧНЫЕ:
        continue
    if из_адресов:
        для_домена += 1
    свои = [(a, p) for a, p in адреса.get(inn, ()) if a.endswith('@' + дом) and p]
    г1, г2 = {}, {}
    for a, p in свои:
        лок = a.split('@')[0]
        i1 = ES.кандидаты(p).get(лок)
        if i1:
            г1[i1] = г1.get(i1, 0) + 1
        i2 = кандидаты2(p).get(лок)
        if i2:
            г2[i2] = г2.get(i2, 0) + 1
    n1 = max(г1.values()) if г1 else 0
    n2 = max(г2.values()) if г2 else 0
    было += n1 >= 2
    стало += n2 >= 2
    if n2 >= 2 > n1:
        новые.append({'инн': inn, 'дом': дом, 'из_адресов': bool(из_адресов),
                      'правило': max(г2, key=г2.get), 'голосов': n2,
                      'адреса': [a for a, _ in свои][:3]})

# общий замер recall на всех парах emails
пары = [((a or '').lower().strip(), p or '') for a, p in e.execute(
    'select email, person from emails where person<>"" and email like "%@%"')]
r1 = sum(1 for a, p in пары if ES.кандидаты(p).get(a.split('@')[0]))
r2 = sum(1 for a, p in пары if кандидаты2(p).get(a.split('@')[0]))
out = {'целей': len(цели), 'правило_было': было, 'правило_стало': стало,
       'новые_компании': новые, 'домен_взят_из_адресов': для_домена,
       'пар_всего': len(пары), 'узнано_было': r1, 'узнано_стало': r2}
print(json.dumps(out, ensure_ascii=False, indent=1)[:9000])
print('ИТОГ ' + json.dumps({k: v for k, v in out.items() if k != 'новые_компании'},
                           ensure_ascii=False))
