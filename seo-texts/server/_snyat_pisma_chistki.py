# -*- coding: utf-8 -*-
"""Снять из очереди письма, построенные на паспортах, снятых чисткой мульти-ИНН.

Критерий точный: ИНН, чей паспорт ушёл в карантин этой чисткой (privyazka
начинается с «мульти-ИНН», «приговор» или «общий домен»). Снимаем канонным
путём панели — status='skipped' с причиной, как делает confirm.skip(), чтобы
письмо не пропало, а легло в разобранные с внятным следом.

    python _snyat_pisma_chistki.py            посчитать
    python _snyat_pisma_chistki.py --primenit снять
"""
import json
import sqlite3
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
применять = '--primenit' in sys.argv
e = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
инны = {str(r[0]) for r in e.execute(
    "select inn from site_facts where coalesce(otkloneno_json,'')<>'' and ("
    "privyazka like 'мульти-ИНН%' or privyazka like 'приговор%' "
    "or privyazka like 'общий домен%')")}
e.close()
s = sqlite3.connect(r'C:\sender\sender.db', timeout=90)
s.row_factory = sqlite3.Row
письма = [dict(r) for r in s.execute(
    "select id, inn, email, campaign_id, subject from confirm_reviews "
    "where status='pending' and inn in (%s)" % ','.join('?' * len(инны)),
    list(инны))] if инны else []
итог = {'инн_с_карантином_паспорта': len(инны), 'pending_писем': len(письма),
        'по_кампаниям': {}}
for п in письма:
    к = str(п['campaign_id'])
    итог['по_кампаниям'][к] = итог['по_кампаниям'].get(к, 0) + 1
итог['примеры'] = [{'инн': п['inn'], 'кому': п['email'],
                    'тема': (п['subject'] or '')[:60]} for п in письма[:6]]
if применять and письма:
    ts = time.strftime('%Y-%m-%dT%H:%M:%S')
    with s:
        for п in письма:
            s.execute("update confirm_reviews set status='skipped', reason=?, "
                      'decided_by=?, decided_at=?, updated_at=? '
                      "where id=? and status='pending'",
                      ('чистка мульти-ИНН 17.08: паспорт снят, сайт чужой/спорный',
                       'sverka-17.08', ts, ts, п['id']))
    итог['снято'] = len(письма)
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1))
