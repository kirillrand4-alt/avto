# -*- coding: utf-8 -*-
"""Насколько вреден несудимый остаток мульти-ИНН привязок ПРЯМО СЕЙЧАС.

Вред возможен только там, где по спорному паспорту может родиться письмо:
компания в группе «Партия 935» (кампании берут кандидатов оттуда) или письмо
уже лежит в очереди подтверждений. Всё остальное — спящий риск: письма не
строятся, адреса в панель не идут.
"""
import json
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
ENRICH = r'C:\sender\enrich.db'
SENDER = r'C:\sender\sender.db'
ОЧЕРЕДИ = (r'C:\sender\_tmp\prigovor-ochered.jsonl',
           r'C:\sender\server\prigovor-ochered.jsonl')

очередь = []
for п in ОЧЕРЕДИ:
    if os.path.exists(п):
        with open(п, encoding='utf-8') as f:
            очередь = [json.loads(l) for l in f if l.strip()]
        break
e = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
судимые = {(str(r[0]), r[1]): r[2] for r in e.execute(
    'select inn, domen, verdikt from prigovor_domenov')}
паспорт_жив = {str(r[0]) for r in e.execute(
    "select inn from site_facts where coalesce(format,0)>=2 "
    "and facts_json like '%\"продукция\": [\"%'")}
e.close()

неосуждены, без_страниц = [], []
for з in очередь:
    в = судимые.get((з['inn'], з['домен']))
    if в in ('свой', 'группа', 'чужой', 'не_понять'):
        continue
    (без_страниц if в == 'нет_страниц' else неосуждены).append(з)

s = sqlite3.connect('file:%s?mode=ro' % SENDER.replace('\\', '/'), uri=True)
s.row_factory = sqlite3.Row
в_группе = set()
for r in s.execute("select coalesce(inn,'') inn, coalesce(extra_json,'') ex "
                   "from recipients where extra_json like '%gruppy%'"):
    try:
        гр = json.loads(r['ex']).get('gruppy') or []
    except Exception:  # noqa: BLE001
        continue
    if 'Партия 935' in гр:
        в_группе.add(''.join(c for c in r['inn'] if c.isdigit()))

итог = {'группа_935_компаний_чисто': len(в_группе)}
for имя, сп in (('неосуждённые_с_кэшем', неосуждены),
                ('неосуждённые_без_страниц', без_страниц)):
    инны = {з['inn'] for з in сп}
    в935 = инны & в_группе
    письма = {}
    if в935:
        для = list(в935)
        for r in s.execute(
                "select campaign_id, count(*) n from confirm_reviews "
                "where status='pending' and inn in (%s) group by 1"
                % ','.join('?' * len(для)), для):
            письма[str(r['campaign_id'])] = r['n']
    итог[имя] = {'компаний': len(инны), 'в_группе_935': len(в935),
                 'с_живым_паспортом': len(инны & паспорт_жив),
                 'в_группе_и_с_паспортом': len(в935 & паспорт_жив),
                 'их_pending_писем_по_кампаниям': письма}
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1))
