# -*- coding: utf-8 -*-
"""Честный счёт группы (разбор JSON, а не LIKE) и поиск компаний, потерявших тег.

LIKE '%Партия 935%' ловит и запись gruppy_ubrano — след СНЯТОГО тега. Из-за
этого дедупликатор мог принять за «лучшего» строку, тега у которой уже нет, а
тег снять с настоящей — и компания выпала бы из партии целиком. Проверяем.
"""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
ГРУППА = 'Партия 935'
САЙТ = "(e.source in ('own-site','zenno') or e.source like 'сайт:%')"
ЧИСТ = ("coalesce(e.pometka,'') not like '%спам-ловушк%' "
        "and coalesce(e.pometka,'') not like '%скрыт%' "
        "and coalesce(e.pometka,'') not like '%не использовать%'")

c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
годные = {str(r[0]) for r in c.execute(
    "select k.inn from companies k where exists(select 1 from emails e "
    'where e.inn=k.inn and %s and %s) and exists(select 1 from site_facts f '
    'where f.inn=k.inn and coalesce(f.format,0)>=2 '
    'and f.facts_json like \'%%"продукция": ["%%\')' % (САЙТ, ЧИСТ))}
c.close()

s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
в_группе, снят_тег = {}, {}
for r in s.execute("select id, coalesce(inn,'') inn, lower(coalesce(email,'')) em, "
                   "coalesce(extra_json,'') ex from recipients "
                   "where extra_json like '%Партия 935%'"):
    инн = ''.join(ch for ch in r['inn'] if ch.isdigit())
    try:
        d = json.loads(r['ex']) if r['ex'].strip() else {}
    except Exception:  # noqa: BLE001
        d = {}
    гр = [str(g) for g in (d.get('gruppy') or [])]
    if ГРУППА in гр:
        в_группе.setdefault(инн, []).append(r['em'])
    elif any(x.get('gruppa') == ГРУППА for x in (d.get('gruppy_ubrano') or [])
             if isinstance(x, dict)):
        снят_тег.setdefault(инн, []).append(r['em'])
s.close()

потеряли = {i: v for i, v in снят_тег.items() if i not in в_группе and i in годные}
итог = {'получателей_в_группе': sum(len(v) for v in в_группе.values()),
        'компаний_в_группе': len(в_группе),
        'компаний_с_дублями': sum(1 for v in в_группе.values() if len(v) > 1),
        'лишних_строк': sum(len(v) - 1 for v in в_группе.values() if len(v) > 1),
        'строк_со_снятым_тегом': sum(len(v) for v in снят_тег.values()),
        'ПОТЕРЯЛИ_группу_хотя_годны': len(потеряли),
        'примеры_потерь': [{'инн': i, 'адреса': v[:2]}
                           for i, v in list(потеряли.items())[:5]]}
print(json.dumps(итог, ensure_ascii=False, indent=1))
