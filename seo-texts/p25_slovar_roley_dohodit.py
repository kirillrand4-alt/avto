# -*- coding: utf-8 -*-
"""Готовый словарь ролей есть. Доходит ли он до выбора адресата письма?

Владелец: «100+ ролей должно быть где-то прописано, это было уже готово, но текущие
опознавалки до этого использовались».

Поиск показал числа, и они говорят сами за себя:

    enrich.db . people . post          3 153 разных должности
    centrifugal.db . person . position 2 204
    tehlpr.db . tehlpr . post            921
    p25.db . person . position           637
    ...
    enrich.db . emails . ROLE              21   <- а ИЗ ЭТОГО выбирается адресат письма

То есть должности собраны тысячами, а выбор получателя опирается на двадцать одно
значение. Прибор проверяет ТРИ вещи и печатает числа:

  1. сколько правил в живом каноне `EnrichDB._ROLE_CANON` и сколько канонических ролей;
  2. сколько людей из `people` (с должностью) имеют ту же почту, что и в `emails`, —
     то есть можно ли обогатить роль адреса настоящей должностью человека;
  3. сколько компаний, у которых best_email имеет роль «общий», при этом В people
     ЛЕЖИТ человек с технической должностью. Это прямая потеря: адресат обезличен,
     а человек известен.

Ничего не меняет.
"""
import collections
import json
import os
import re
import sqlite3
import sys

ENRICH = r'C:\sender\enrich.db'
TEH = re.compile(r'главн\w*\s+(?:инженер|энергетик|механик|технолог|метролог)|'
                 r'гл\.?\s*(?:инженер|энергетик|механик|технолог|метролог)|'
                 r'технич\w*\s+директор|техдиректор|'
                 r'начальник\w*\s+(?:цеха|производств|отдела\s+снабж|отк|котельн|'
                 r'энерго|ремонт|тэц|компрессорн)|'
                 r'энергетик|механик|метролог|асу|кипиа|'
                 r'снабжен|закупк|тендер', re.I)
NE_NASH = re.compile(r'кадр|персонал|подбор|ваканс|пресс|юрис|бухгалт|реклам|маркет|'
                     r'охран\w*\s+труда|качеств|эколог|сервис|претенз|гарантийн', re.I)

sys.path.insert(0, r'C:\sender\server')
print('=== 1. Живой канон ролей')
try:
    import enrich_db as EDB
    kanon = EDB.EnrichDB._ROLE_CANON
    n_pravil = len(kanon)
    n_klyuchey = sum(len(k) for k, _ in kanon)
    roli = sorted({v for _, v in kanon})
    print('  файл канона: %s' % EDB.__file__)
    print('  правил %d, ключей %d, канонических ролей %d' % (n_pravil, n_klyuchey,
                                                             len(roli)))
    print('  роли: %s' % ', '.join(roli))
except Exception as e:  # noqa: BLE001
    print('  канон не импортировался: %s' % str(e)[:90])
    n_pravil = n_klyuchey = 0
    roli = []

cx = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
tabl = [r[0] for r in cx.execute("select name from sqlite_master where type='table'")]
print('\n=== 2. people против emails')
sch = collections.Counter()
if 'people' in tabl:
    p_kol = [r[1] for r in cx.execute('pragma table_info(people)')]
    print('  people колонки: %s' % ', '.join(p_kol))
    e_mail = 'email' if 'email' in p_kol else ''
    sch['людей в people'] = cx.execute('select count(*) from people').fetchone()[0]
    sch['  с должностью'] = cx.execute(
        'select count(*) from people where coalesce(post,"")<>""').fetchone()[0]
    sch['  разных должностей'] = cx.execute(
        'select count(distinct post) from people where coalesce(post,"")<>""').fetchone()[0]
    if e_mail:
        sch['  с почтой'] = cx.execute(
            'select count(*) from people where coalesce(email,"")<>""').fetchone()[0]

    # 3. Компании, где best_email общий, а технарь в people ЛЕЖИТ
    lyudi = collections.defaultdict(list)
    polya = [x for x in ('inn', 'post', 'name', 'fio', 'person', 'email') if x in p_kol]
    for r in cx.execute('select %s from people' % ','.join(polya)):
        z = dict(zip(polya, r))
        if str(z.get('post') or '').strip():
            lyudi[str(z.get('inn'))].append(z)

    roli_adresov = {}
    for r in cx.execute('select inn, lower(coalesce(email,"")), coalesce(role,"") '
                        'from emails'):
        roli_adresov[(str(r[0]), r[1])] = r[2]

    poteryano = []
    for r in cx.execute('select inn, coalesce(best_email,""), coalesce(name,"") '
                        'from companies where coalesce(best_email,"")<>"" '
                        'and coalesce(is_competitor,0)=0'):
        inn, be = str(r[0]), (r[1] or '').lower()
        rol = (roli_adresov.get((inn, be)) or '').strip().lower()
        if rol not in ('', 'общий', 'приёмная', 'приемная'):
            continue
        teh = [z for z in lyudi.get(inn, [])
               if TEH.search(str(z.get('post') or ''))
               and not NE_NASH.search(str(z.get('post') or ''))]
        if teh:
            poteryano.append((inn, r[2][:26], be[:26], rol or 'без роли',
                              str(teh[0].get('post'))[:34],
                              str(teh[0].get('name') or teh[0].get('fio')
                                  or teh[0].get('person') or '')[:24]))
    sch['КОМПАНИЙ: адресат обезличен, а технарь В people ЕСТЬ'] = len(poteryano)
    print('\n=== 3. адресат общий, а человек с технической должностью известен')
    for x in poteryano[:14]:
        print('   ' + ' | '.join(str(y)[:30] for y in x))
    if not poteryano:
        print('   ни одного')
cx.close()
print()
for k, v in sch.items():
    print('REC %s\t%s' % (k, v))
print('ИТОГ ' + json.dumps({
    'правил в каноне': n_pravil, 'канонических ролей': len(roli),
    'разных должностей в people': sch.get('  разных должностей', 0),
    'адресат обезличен при известном технаре': sch.get(
        'КОМПАНИЙ: адресат обезличен, а технарь В people ЕСТЬ', 0)}, ensure_ascii=False))
