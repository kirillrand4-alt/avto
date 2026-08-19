# -*- coding: utf-8 -*-
"""Домены из почт БАЗЫ ОБЗВОНА: сколько компаний можно достать через них."""
import json
import os
import re
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
FREEMAIL = {'mail.ru', 'yandex.ru', 'ya.ru', 'gmail.com', 'bk.ru', 'list.ru',
            'inbox.ru', 'rambler.ru', 'internet.ru', 'mail.com', 'icloud.com',
            'outlook.com', 'hotmail.com', 'yahoo.com', 'vk.com', 'narod.ru',
            'mail.ru.', 'bk.ru.'}
СЛУЖЕБНЫЙ = re.compile(
    r'(^|\.)(gov|gosuslugi|nalog|tensor|sbis|kontur|diadoc|taxcom|astral|'
    r'bashneft|mechel|rzd|rosneft|gazprom|lukoil|sberbank|vtb)\.', re.I)
ZENNO = r'C:\seostat\drop\zenno'
KESH = r'C:\seostat\drop\pagecache'
отдано = {l.strip() for l in open(os.path.join(ZENNO, 'otdano.txt'),
                                  encoding='utf-8', errors='replace') if l.strip()}
обойдено = {n.split('.')[0] for n in os.listdir(KESH) if n.endswith('.json.gz')}
o = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/obzvon-index.db', uri=True)
кол = [r[1] for r in o.execute('pragma table_info(obzvon)')]
итог = {'колонки_с_почтой': [k for k in кол if 'mail' in k.lower()],
        'строк_всего': o.execute('select count(*) from obzvon').fetchone()[0]}
поля = [k for k in кол if 'mail' in k.lower()]
запрос = ("select inn, coalesce(sites,''), %s from obzvon"
          % ', '.join("coalesce(%s,'')" % k for k in поля))
свод = {'без_сайта_но_с_почтой': 0, 'годных_доменов': 0, 'freemail': 0,
        'служебные': 0, 'уже_обойдены': 0, 'уже_отдавали': 0}
кандидаты = []
for строка in o.execute(запрос):
    inn = ''.join(c for c in str(строка[0] or '') if c.isdigit())
    сайты = str(строка[1] or '').strip()
    почты = ' '.join(str(x or '') for x in строка[2:])
    if not inn or сайты:
        continue
    адреса = re.findall(r'[\w.+-]+@([\w.-]+\.[a-zA-Zрф]{2,})', почты)
    if not адреса:
        continue
    свод['без_сайта_но_с_почтой'] += 1
    if inn in обойдено:
        свод['уже_обойдены'] += 1
        continue
    if inn in отдано:
        свод['уже_отдавали'] += 1
        continue
    выбор = ''
    for d in адреса:
        d = d.lower().strip('.')
        if d in FREEMAIL:
            continue
        if СЛУЖЕБНЫЙ.search(d):
            свод['служебные'] += 1
            continue
        выбор = d
        break
    if not выбор:
        свод['freemail'] += 1
        continue
    свод['годных_доменов'] += 1
    кандидаты.append('%s;%s;oba' % (inn, выбор))
o.close()
итог.update(свод)
итог['примеры'] = кандидаты[:5]
if '--pisat' in sys.argv and кандидаты:
    for путь, данные in ((os.path.join(ZENNO, 'ochered.txt'), кандидаты),
                         (os.path.join(ZENNO, 'otdano.txt'),
                          [s.split(';')[0] for s in кандидаты])):
        with open(путь, 'a', encoding='utf-8') as f:
            f.write('\n'.join(данные) + '\n')
            f.flush()
            os.fsync(f.fileno())
    итог['дописано'] = len(кандидаты)
print(json.dumps(итог, ensure_ascii=False, indent=1))
