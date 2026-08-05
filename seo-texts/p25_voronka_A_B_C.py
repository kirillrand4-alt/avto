# -*- coding: utf-8 -*-
"""Воронка A→B→C и турникет по ЧЕСТНЫМ полям. Прошлый счёт Д3 был неправдой.

Я насчитала «507 готовых к генерации». Число крупное, поэтому проверила прибор — и он
врал: графу «адрес доказан» я считала по таблице `emails`, а колонки `verified` там НЕТ
ВООБЩЕ (есть `addr_class`). «Доказан» выродилось в «почта есть». Настоящее `verified`
лежит в `companies`, и там же те 77 писем со статусом `mismatch`, которые нашла 2-я
сессия.

Считаю заново, называя поле у каждой графы:

    A  собрано      signals: строк, разных ИНН
    A1 повод        мера повода: ПРЯМОЙ / КОСВЕННЫЙ / ЧУЖОЙ         (моя, 3-я сессия)
    B  юрлицо       companies.verified                              (2-я сессия)
    B2 принадлежн.  people.prinadlezhnost_chem                      (2-я сессия)
    C  контакт+роль people.person + people.post/role                (1-я сессия)

Турникет = пересечение по ИНН, и печатается, кто именно отваливается на каждом шаге:
ноль тоже ответ, но с причиной по графам.

Только чтение.
"""
import collections
import json
import os
import re
import sqlite3

ENRICH = r'C:\sender\enrich.db'
SENDER = r'C:\sender\sender.db'

MASHINA = re.compile(
    r'компрессор\w*|турбокомпрессор\w*|газодувк\w+|газодувн\w+|воздуходувк\w+|'
    r'нагнетател\w+|воздухоразделен\w+|\bВРУ\b|сжат\w+\s+воздух\w*|пневмат\w+|'
    r'генератор\w*\s+(?:азота|кислорода)|азотн\w+\s+станци\w+|кислородн\w+\s+станци\w+|'
    r'\bазот\w*\b|\bкислород\w*\b|\bчиллер\w*', re.I)
PROIZVODSTVO = re.compile(
    r'\b\w*завод\w*|\bцех\w*|\bпроизводств\w*|\b\w*комбинат\w*|\bфабрик\w*|\bэлеватор\w*|'
    r'\bпроизводственн\w+|\bмощност\w+\s+\d|\bагрегат\w*|\bустановк\w+|\bпереработк\w+|'
    r'\bобогатительн\w+|\bметаллург\w+|\bНПЗ\b|\bГОК\b|\bТЭЦ\b|\bдобыч\w+|\bшахт\w+', re.I)
CHUZHOE = re.compile(
    r'\bлогистическ\w+\s+(?:комплекс\w*|центр\w*)|\bсклад\w+\s+комплекс\w*|'
    r'\bторгов\w+\s+центр\w*|\bжил\w+\s+(?:комплекс\w*|дом\w*)|\bдетск\w+\s+сад\w*|'
    r'\bшкол\w+|\bбольниц\w+|\bполиклиник\w+|\bфельдшерск\w+|\bФАП\b|\bстадион\w*|'
    r'\bавтосалон\w*|\bофисн\w+\s+здани\w+|\bблагоустройств\w+|\bмост\b|\bтротуар\w*', re.I)
VAKANSIYA = re.compile(r'нанимает|ваканси|ищет\s+«|машинист|слесарь|оператор\s+', re.I)


def povod(t):
    t = t or ''
    if MASHINA.search(t):
        return 'ПРЯМОЙ'
    if PROIZVODSTVO.search(t):
        return 'КОСВЕННЫЙ'
    if CHUZHOE.search(t):
        return 'ЧУЖОЙ'
    return 'КОСВЕННЫЙ'


def chelovek(s):
    s = re.sub(r'\s+', ' ', str(s or '')).strip()
    if len(s.split()) < 2:
        return False
    if re.search(r'отдел|департамент|служб|управлени|респ\b|обл\b|кра[йя]\b|район|'
                 r'ООО|АО\b|ЗАО|ПАО|филиал', s, re.I):
        return False
    return bool(re.match(r'^[А-ЯЁ][а-яё\-]+\s+[А-ЯЁ]', s))


cx = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)

# --- A ---------------------------------------------------------------------------------
vsego = cx.execute('select count(*) from signals').fetchone()[0]
inn_vseh = set()
po_povodu = collections.Counter()
inn_po_povodu = collections.defaultdict(set)
inn_vakansiya, inn_novost = set(), set()
for inn, what, ist in cx.execute('select inn, what, source from signals'):
    i = str(inn or '').strip()
    if i:
        inn_vseh.add(i)
    u = povod(what or '')
    po_povodu[u] += 1
    if i and u != 'ЧУЖОЙ':
        inn_po_povodu[u].add(i)
        (inn_vakansiya if VAKANSIYA.search(what or '') or 'hh' in str(ist or '').lower()
         else inn_novost).add(i)

A_godnye = inn_po_povodu['ПРЯМОЙ'] | inn_po_povodu['КОСВЕННЫЙ']
print('=== A. СОБРАНО')
print('  сигналов %d, разных ИНН %d' % (vsego, len(inn_vseh)))
print('  по поводу: %s' % dict(po_povodu))
print('  ИНН с годным поводом: %d (прямых %d, косвенных %d)'
      % (len(A_godnye), len(inn_po_povodu['ПРЯМОЙ']), len(inn_po_povodu['КОСВЕННЫЙ'])))
print('  из них повод = ВАКАНСИЯ %d, повод = НОВОСТЬ %d'
      % (len(inn_vakansiya), len(inn_novost)))

# --- B ---------------------------------------------------------------------------------
kol_c = [r[1] for r in cx.execute('pragma table_info(companies)')]
print('\n=== B. ЮРЛИЦО (поле companies.verified)')
sch_v = collections.Counter()
inn_ver_ok, inn_mismatch = set(), set()
for inn, v in cx.execute('select inn, verified from companies'):
    i = str(inn or '').strip()
    vv = str(v or '').strip()
    sch_v[vv or '(пусто)'] += 1
    if not i:
        continue
    if vv == 'mismatch':
        inn_mismatch.add(i)
    elif vv in ('inn', 'phone'):
        inn_ver_ok.add(i)
for k, n in sch_v.most_common():
    print('  verified=%-14s %6d' % (k, n))
print('  ИНН с verified inn/phone: %d ; с mismatch: %d'
      % (len(inn_ver_ok), len(inn_mismatch)))

print('\n=== B2. ПРИНАДЛЕЖНОСТЬ ЧЕЛОВЕКА ЮРЛИЦУ (people.prinadlezhnost_chem)')
kol_p = [r[1] for r in cx.execute('pragma table_info(people)')]
if 'prinadlezhnost_chem' in kol_p:
    sila = collections.Counter()
    inn_silno = set()
    for inn, pi, ch in cx.execute(
            'select inn, prinadlezhnost_inn, prinadlezhnost_chem from people'):
        c = str(ch or '').strip()
        if not c:
            sila['(пусто)'] += 1
            continue
        if re.search(r'ЕГРЮЛ|карточк\w*\s+закупк|контактн\w*\s+лиц', c, re.I):
            sila['сильное'] += 1
            if str(pi or '').strip():
                inn_silno.add(str(pi).strip())
        elif re.search(r'РТН|ростехнадзор|протокол', c, re.I):
            sila['среднее'] += 1
        elif re.search(r'домен|сайт', c, re.I):
            sila['слабое'] += 1
        else:
            sila['иное: %s' % c[:28]] += 1
    for k, n in sila.most_common(10):
        print('  %-30s %6d' % (k, n))
    print('  ИНН с СИЛЬНЫМ доказательством: %d' % len(inn_silno))
else:
    inn_silno = set()
    print('  графы нет')

# --- C ---------------------------------------------------------------------------------
print('\n=== C. КОНТАКТ + РОЛЬ (people.person / post / role)')
inn_chel, inn_chel_rol = set(), set()
n_strok = n_chel = 0
roli = collections.Counter()
for inn, person, post, role in cx.execute('select inn, person, post, role from people'):
    n_strok += 1
    i = str(inn or '').strip()
    if not chelovek(person):
        continue
    n_chel += 1
    if i:
        inn_chel.add(i)
        r = (str(post or '') + ' ' + str(role or '')).strip()
        roli[r[:34] or '(без роли)'] += 1
        if r:
            inn_chel_rol.add(i)
print('  строк %d, похожих на человека %d, разных ИНН %d, с ролью %d ИНН'
      % (n_strok, n_chel, len(inn_chel), len(inn_chel_rol)))
print('  --- 10 самых частых ролей')
for k, n in roli.most_common(10):
    print('    %-36s %5d' % (k, n))
cx.close()

# --- турникет --------------------------------------------------------------------------
print('\n=== ТУРНИКЕТ (пересечения по ИНН)')
shagi = [('A повод годный', A_godnye),
         ('B verified inn/phone', inn_ver_ok),
         ('B2 принадлежность сильная', inn_silno),
         ('C человек с ролью', inn_chel_rol)]
tek = None
for imya, mn in shagi:
    tek = mn if tek is None else (tek & mn)
    print('  %-28s своих %6d   накопленное пересечение %6d' % (imya, len(mn), len(tek)))
gotovo = tek - inn_mismatch
print('  минус mismatch (%d)          ИТОГО ГОТОВО К ГЕНЕРАЦИИ %6d'
      % (len(inn_mismatch), len(gotovo)))
print('\n  --- почему отваливаются: у скольких годный повод, но нет')
print('    B verified          %6d' % len(A_godnye - inn_ver_ok))
print('    B2 принадлежности   %6d' % len(A_godnye - inn_silno))
print('    C человека с ролью  %6d' % len(A_godnye - inn_chel_rol))

if os.path.exists(SENDER):
    cs = sqlite3.connect('file:%s?mode=ro' % SENDER.replace('\\', '/'), uri=True)
    print('\n=== ОЧЕРЕДЬ ПАНЕЛИ')
    for st, n in cs.execute('select status, count(*) from messages group by status'):
        print('  messages %-18s %d' % (str(st)[:18], n))
    cs.close()

print('\nИТОГ ' + json.dumps({'A годных ИНН': len(A_godnye),
                              'B verified': len(inn_ver_ok),
                              'B2 сильных': len(inn_silno),
                              'C человек с ролью': len(inn_chel_rol),
                              'ГОТОВО': len(gotovo),
                              'mismatch': len(inn_mismatch)}, ensure_ascii=False))
