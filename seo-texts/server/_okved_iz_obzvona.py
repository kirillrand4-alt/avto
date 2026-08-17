# -*- coding: utf-8 -*-
"""Есть ли ОКВЭД пропавших компаний в базе обзвона — прежде чем платить за checko."""
import json
import sqlite3
import sys

BD = r'C:\sender\enrich.db'
OBZVON = r'C:\sender\obzvon-index.db'

o = sqlite3.connect(OBZVON)
колонки = [r[1] for r in o.execute('pragma table_info(obzvon)')]
поле = next((k for k in колонки if 'okved' in k.lower() or 'оквэд' in k.lower()), '')

c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
без = [str(r[0]) for r in c.execute(
    "select k.inn from companies k join site_facts f on f.inn=k.inn "
    "where coalesce(f.facts_json,'')<>'' and coalesce(k.okved,'')=''")]
c.close()

итог = {'колонки_обзвона': колонки, 'поле_оквэд': поле or '(нет такого поля)',
        'без_оквэда_в_нашей_базе': len(без)}
if поле:
    есть, примеры = 0, []
    for i in range(0, len(без), 400):
        часть = без[i:i + 400]
        q = ','.join('?' * len(часть))
        for inn, ок in o.execute(
                "select inn, coalesce(%s,'') from obzvon where inn in (%s)" % (поле, q), часть):
            if str(ок).strip():
                есть += 1
                if len(примеры) < 8:
                    примеры.append({'инн': str(inn), 'оквэд': str(ок)[:60]})
    итог['из_них_оквэд_есть_в_обзвоне'] = есть
    итог['примеры'] = примеры
o.close()
sys.stdout.reconfigure(encoding='utf-8')
print(json.dumps(итог, ensure_ascii=False, indent=1))
