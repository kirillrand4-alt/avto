# -*- coding: utf-8 -*-
"""Свод типов к канону. Встречная проверка исключений вернула 588 фактов, и модель
называла тип свободными словами: «промышленные компрессоры», «промышленный компрессор
(поршневой)», «ресиверы сжатого воздуха». В выдаче это тринадцать разных строк вместо
одной, и владелец в фильтре по типу их не найдёт.

Канон (13 типов) остаётся прежним; принцип действия (винтовой/поршневой/центробежный)
не выбрасываем, а кладём в отдельное поле princip — он ценен для разговора.
"""
import sqlite3, re, os, collections
D = os.path.dirname(os.path.abspath(__file__))
p = sqlite3.connect(os.path.join(D, 'park.db')); cur = p.cursor()
if 'princip' not in [c[1] for c in cur.execute('pragma table_info(fakt)')]:
    cur.execute('alter table fakt add column princip TEXT')

KANON = [
    (r'мкс|модульн\w*\s*компрессорн', 'МКС'),
    (r'\bпкс\b|передвижн\w*\s*компрессорн|дизельн\w*\s*компрессорн', 'ПКС'),
    (r'\bгпа\b|газоперекачив', 'ГПА'),
    (r'\bвру\b|воздухораздел', 'ВРУ'),
    (r'генератор\w*\s*(и\s*)?кислород|кислородн\w*\s*(станци|установк|генератор)', 'генератор кислорода'),
    (r'генератор\w*\s*азот|азотн\w*\s*(станци|установк|генератор)', 'генератор азота'),
    (r'турбокомпрессор', 'турбокомпрессор'),
    (r'нагнетател', 'нагнетатель'),
    (r'воздуходувк|газодувк', 'воздуходувка'),
    (r'осушител', 'осушитель'),
    (r'ресивер|воздухосборник', 'ресивер'),
    (r'компрессорн\w*\s*(станци|установк)', 'компрессорная станция'),
    (r'компрессор', 'компрессор'),
]
PRINCIP = [(r'винтов', 'винтовой'), (r'поршнев', 'поршневой'),
           (r'центробежн', 'центробежный'), (r'безмаслян', 'безмасляный'),
           (r'мембранн', 'мембранный'), (r'спиральн', 'спиральный')]

izm = collections.Counter(); pri = 0
for fid, tip in cur.execute("select id, tip from fakt where coalesce(tip,'')<>''").fetchall():
    t = tip.lower().replace('ё', 'е')
    novyy = next((k for rx, k in KANON if re.search(rx, t)), None)
    princip = next((k for rx, k in PRINCIP if re.search(rx, t)), None)
    if princip:
        cur.execute('update fakt set princip=coalesce(nullif(princip,""),?) where id=?',
                    (princip, fid)); pri += 1
    if novyy and novyy != tip:
        cur.execute('update fakt set tip=? where id=?', (novyy, fid))
        izm['%s -> %s' % (tip, novyy)] += 1
p.commit()
print('переименовано фактов: %d' % sum(izm.values()))
for k, n in izm.most_common(14): print('   %5d  %s' % (n, k))
print('принцип действия проставлен фактам:', pri)
c = collections.Counter(r[0] for r in cur.execute('select tip from fakt where v_parke=1'))
print('\nтипов в парке стало: %d' % len(c))
for t, n in c.most_common(20): print('   %6d  %s' % (n, t))
p.close()
