# -*- coding: utf-8 -*-
"""Компании без известного сайта, но с почтой на собственном домене."""
import json
import os
import re
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\sender\server')
ZENNO = r'C:\seostat\drop\zenno'
KESH = r'C:\seostat\drop\pagecache'
FREEMAIL = {'mail.ru', 'yandex.ru', 'ya.ru', 'gmail.com', 'bk.ru', 'list.ru',
            'inbox.ru', 'rambler.ru', 'internet.ru', 'mail.com', 'icloud.com',
            'outlook.com', 'hotmail.com', 'yahoo.com', 'vk.com', 'narod.ru'}
отдано = {l.strip() for l in open(os.path.join(ZENNO, 'otdano.txt'),
                                  encoding='utf-8', errors='replace') if l.strip()}
обойдено = {n.split('.')[0] for n in os.listdir(KESH) if n.endswith('.json.gz')}
try:
    import ploshchadki as PL
    площадка = PL.из_списка
except Exception:  # noqa: BLE001
    площадка = lambda u: ''
СЛУЖЕБНЫЙ = re.compile(
    r'(^|\.)(gov|gosuslugi|nalog|tensor|sbis|kontur|diadoc|taxcom|astral|'
    r'bashneft|mechel|rzd|rosneft|gazprom|lukoil|sberbank|vtb)\.',
    re.I)
итог = {'кандидатов': 0, 'уже_отдавали': 0, 'уже_обойдены': 0,
        'freemail_пропущено': 0, 'площадки': 0, 'домены': {}}
e = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
# домены, уже закреплённые за КАКОЙ-ЛИБО компанией: если почта ведёт на такой,
# это чужой сайт, а не наш кандидат
занятые_домены = set()
for (u,) in e.execute("select coalesce(site,'') from companies where coalesce(site,'')<>'' "
                      "union select coalesce(cand_site,'') from companies "
                      "where coalesce(cand_site,'')<>''"):
    d = re.sub(r'^https?://', '', str(u or '')).split('/')[0].lower()
    d = d[4:] if d.startswith('www.') else d
    if d:
        занятые_домены.add(d)
новые = []
for inn, домены in e.execute(
        "select e.inn, group_concat(distinct lower(substr(e.email, instr(e.email,'@')+1))) "
        "from emails e join companies k on k.inn=e.inn "
        "where coalesce(k.site,'')='' and coalesce(k.cand_site,'')='' "
        "and coalesce(e.email,'')<>'' group by e.inn"):
    inn = str(inn)
    if inn in обойдено:
        итог['уже_обойдены'] += 1
        continue
    if inn in отдано:
        итог['уже_отдавали'] += 1
        continue
    выбор = ''
    for d in (домены or '').split(','):
        d = d.strip()
        if not d or d in FREEMAIL or '.' not in d:
            continue
        if площадка(d):
            итог['площадки'] += 1
            continue
        # СЛУЖЕБНЫЕ И ЧУЖИЕ ДОМЕНЫ. Домен из почты — подсказка слабая: у малого
        # юрлица почта часто на портале администрации (adygheya.gov.ru), на
        # сервисе отчётности (eo.tensor.ru, sbis, diadoc) или на домене холдинга
        # (bashneft.ru, mechel.com). Обойти такой сайт — собрать паспорт чужого
        # предприятия, ровно та беда, которую мы весь день вычищали.
        if СЛУЖЕБНЫЙ.search(d):
            итог['служебные'] = итог.get('служебные', 0) + 1
            continue
        if d in занятые_домены:
            итог['домен_уже_чей_то'] = итог.get('домен_уже_чей_то', 0) + 1
            continue
        выбор = d
        break
    if not выбор:
        итог['freemail_пропущено'] += 1
        continue
    итог['кандидатов'] += 1
    новые.append('%s;%s;oba' % (inn, выбор))
    итог['домены'][выбор] = итог['домены'].get(выбор, 0) + 1
e.close()
итог['примеры'] = новые[:5]
итог['доменов_разных'] = len(итог['домены'])
итог.pop('домены')
if '--pisat' in sys.argv and новые:
    for путь, данные in ((os.path.join(ZENNO, 'ochered.txt'), новые),
                         (os.path.join(ZENNO, 'otdano.txt'),
                          [s.split(';')[0] for s in новые])):
        with open(путь, 'a', encoding='utf-8') as f:
            f.write('\n'.join(данные) + '\n')
            f.flush()
            os.fsync(f.fileno())
    итог['дописано'] = len(новые)
print(json.dumps(итог, ensure_ascii=False, indent=1))
