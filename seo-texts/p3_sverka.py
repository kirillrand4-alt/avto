# -*- coding: utf-8 -*-
"""СВЕРКА: что на самом деле лежит в живой enrich.db после перелива. Только чтение.

Крупное число — повод проверить прибор: числа сборщика проверяются отдельным
подключением к живой базе, а не берутся из его же вывода.
"""
import sqlite3

con = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True)
con.row_factory = sqlite3.Row
tabl = [r[0] for r in con.execute(
    "select name from sqlite_master where type='table' order by name")]
print('таблиц в живой базе: %d' % len(tabl))
print('мои новые: %s' % [t for t in tabl if t.startswith('proek')])
print('signals: %d строк (не трогали)'
      % con.execute('select count(*) from signals').fetchone()[0])
for t in ('proekty', 'proekt_uliki', 'proekt_slovar', 'proekt_gashenie'):
    print('  %-16s %6d' % (t, con.execute('select count(*) from %s' % t).fetchone()[0]))

print('подтверждённых 2+ источниками: %d'
      % con.execute('select count(*) from proekty where istochnikov>=2').fetchone()[0])
print('одиночных: %d'
      % con.execute('select count(*) from proekty where ulik=1').fetchone()[0])
print('приоритетная отрасль: %d'
      % con.execute('select count(*) from proekty where otrasl_prior=1').fetchone()[0])
print('сумма улик по карточкам = %d, строк в proekt_uliki = %d (должно совпасть)'
      % (con.execute('select sum(ulik) from proekty').fetchone()[0],
         con.execute('select count(*) from proekt_uliki').fetchone()[0]))
sirot = con.execute('select count(*) from proekt_uliki u where not exists '
                    '(select 1 from proekty p where p.proekt_id=u.proekt_id)').fetchone()[0]
print('улик без карточки (сирот): %d — должно быть 0' % sirot)
pust = con.execute("select count(*) from proekty where istochniki=''").fetchone()[0]
print('карточек без источников: %d — должно быть 0' % pust)
print('ИНН 7709329253: проектов %d'
      % con.execute("select count(*) from proekty where inn='7709329253'").fetchone()[0])
print('ТОП-5 по числу источников:')
for r in con.execute('select proekt_id, zakazchik, mesto, stadiya, ulik, istochnikov, '
                     'otrasl, summa_rub from proekty order by istochnikov desc, ulik desc '
                     'limit 5'):
    print('  %s %-30s %-16s %-22s улик %2d ист %2d  %s  %s'
          % (r[0], (r[1] or '')[:30], (r[2] or '—')[:16], r[3][:22], r[4], r[5],
             (r[6] or '—')[:24], ('%.1f млрд' % (r[7] / 1e9)) if r[7] else ''))
print('ПРИМЕР УЛИК одного проекта (источник, дата, ссылка):')
pid = con.execute('select proekt_id from proekty order by istochnikov desc limit 1'
                  ).fetchone()[0]
for r in con.execute('select source, data_sobytiya, source_url, length(citata) from '
                     'proekt_uliki where proekt_id=? limit 6', (pid,)):
    print('  %-22s %-10s %-52s цитата %d знаков'
          % (r[0][:22], r[1] or '—', (r[2] or '')[:52], r[3]))
