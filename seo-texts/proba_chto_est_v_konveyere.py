# -*- coding: utf-8 -*-
"""Что из «сигналов проекта» уже вшито в наш конвейер, а чего нет — по КОДУ сервера.

Владелец принёс список открытых реестров (ЕГРЗ, разрешения на строительство, ЕИС и ЭТП,
господдержка/ФРП/СПИК/ОЭЗ/СЗПК, Федресурс, публичные слушания, соглашения ПМЭФ) и спросил,
что у нас есть, чего нет. Отвечать по памяти нельзя: половина каналов живёт на сервере и в
git их нет.

Прибор смотрит в живые модули: какие коллекторы объявлены в news_scan, и упоминается ли
каждый реестр в коде вообще. Упоминание — не работа, поэтому рядом печатается, в каком
файле и какой строкой, чтобы отличить рабочий коллектор от комментария.
"""
import os
import re
import sys

sys.path.insert(0, r'C:\sender\server')

FAYLY = [r'C:\sender\server\news_scan.py', r'C:\sender\server\enrich_contacts.py',
         r'C:\sender\server\enrich_db.py', r'C:\sender\_ops\people_sources.py',
         r'C:\sender\server\lpr_serp.py', r'C:\sender\server\job_runner.py',
         r'C:\sender\server\news_cron.py']

print('### 1. Коллекторы news_scan — что объявлено в коде\n')
try:
    import news_scan as NS
    imena = [n for n in dir(NS) if n.startswith('col_') or 'collect' in n.lower()]
    print('  функции сбора: %s' % ', '.join(sorted(imena)))
    src = open(r'C:\sender\server\news_scan.py', encoding='utf-8', errors='replace').read()
    for m in re.finditer(r'COLLECTORS\s*=\s*[\{\[\(](.{0,600}?)[\}\]\)]', src, re.S):
        print('  список COLLECTORS: %s' % re.sub(r'\s+', ' ', m.group(1))[:500])
    for m in re.finditer(r"def (col_\w+)\((.*?)\):", src):
        print('     %-26s(%s)' % (m.group(1), m.group(2)[:60]))
except Exception as e:  # noqa: BLE001
    print('  news_scan не подгрузился: %s' % str(e)[:120])

print('\n### 2. Упоминания реестров из списка владельца — по всем живым модулям\n')
SLOVA = [
    ('ЕГРЗ / egrz.ru', r'egrz|ЕГРЗ'),
    ('разрешения на строительство / ГИСОГД', r'gisogd|ИСОГД|стройнадзор|разрешени\w* на строит'),
    ('ЕИС zakupki.gov.ru', r'zakupki\.gov\.ru'),
    ('B2B-Center', r'b2b-?center'),
    ('ТЭК-Торг', r'tektorg|ТЭК-Торг'),
    ('РТС-тендер', r'rts-tender|РТС'),
    ('Сбер-АСТ', r'sberbank-ast|Сбер-?АСТ'),
    ('Росэлторг', r'roseltorg|Росэлторг'),
    ('ЭТП ГПБ', r'etpgpb'),
    ('ФРП frprf.ru', r'frprf|ФРП|\bfrp\b'),
    ('Минпромторг / СПИК', r'СПИК|minpromtorg'),
    ('ОЭЗ / ТОР / СЗПК', r'\bОЭЗ\b|\bСЗПК\b|территори\w* опережающ'),
    ('инвестпорталы, корпорации развития', r'инвестпортал|корпораци\w* развития|инвестпроект'),
    ('Федресурс fedresurs.ru', r'fedresurs|Федресурс'),
    ('публичные слушания / ППТ / генплан', r'публичн\w* слушан|генплан|градсовет|\bППТ\b'),
    ('ПМЭФ / ВЭФ / КЭФ, соглашения', r'ПМЭФ|\bВЭФ\b|\bКЭФ\b|соглашени\w* о намерен'),
    ('Ростехнадзор / ЭПБ', r'monitor-pb|gosnadzor|ЭПБ'),
    ('hh.ru (вакансии как сигнал)', r'hh\.ru|api\.hh'),
]
for imya, pat in SLOVA:
    rx = re.compile(pat, re.I)
    nashlos = []
    for put in FAYLY:
        if not os.path.exists(put):
            continue
        try:
            txt = open(put, encoding='utf-8', errors='replace').read()
        except Exception:  # noqa: BLE001
            continue
        stroki = [i + 1 for i, s in enumerate(txt.splitlines()) if rx.search(s)]
        if stroki:
            nashlos.append('%s: %d упом. (стр. %s)'
                           % (os.path.basename(put), len(stroki),
                              ', '.join(str(x) for x in stroki[:4])))
    print('  %-38s %s' % (imya, '; '.join(nashlos) if nashlos else 'НЕ УПОМИНАЕТСЯ НИГДЕ'))

print('\n### 3. Сколько сигналов каждого вида уже лежит в базе\n')
try:
    import sqlite3
    db = sqlite3.connect(r'C:\sender\enrich.db')
    c = db.cursor()
    tabl = [r[0] for r in c.execute(
        "select name from sqlite_master where type='table'").fetchall()]
    nuzhno = [t for t in tabl if re.search(r'news|signal|sobyt', t, re.I)]
    print('  таблицы про новости/сигналы: %s' % (', '.join(nuzhno) or '—'))
    for t in nuzhno[:4]:
        try:
            n = c.execute('select count(*) from "%s"' % t).fetchone()[0]
            print('     %-22s строк %d' % (t, n))
            kol = [x[1] for x in c.execute('pragma table_info("%s")' % t).fetchall()]
            print('        колонки: %s' % ', '.join(kol)[:150])
            for pole in ('source', 'istochnik', 'collector', 'kanal'):
                if pole in kol:
                    for zn, k in c.execute(
                            'select "%s", count(*) from "%s" group by 1 order by 2 desc limit 12'
                            % (pole, t)).fetchall():
                        print('        %-24s %6d' % (str(zn)[:24], k))
                    break
        except Exception as e:  # noqa: BLE001
            print('     %s — не прочиталась: %s' % (t, str(e)[:60]))
except Exception as e:  # noqa: BLE001
    print('  базу не открыть: %s' % str(e)[:120])
