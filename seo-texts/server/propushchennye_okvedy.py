# -*- coding: utf-8 -*-
r"""Какие ОКВЭДы список владельца пропустил — считаем по улике с сайта.

Владелец 16.08, два сообщения подряд:
    «список целевых ОКВЭД я составлял вручную, мог какие-то вообще не учесть»
    «если компания явно покупает компрессоры — она нам нужна»

Второе важнее первого и переворачивает отбор: решает не код в реестре, а то, что
предприятие САМО написало у себя на сайте. Код — предположение о потребности,
паспорт — улика.

Поэтому считаем так: берём все паспорта, где есть признак КЦ (сжатый воздух или
технические газы, строки дословные — их собирает razlozhit_energohozyaystvo), и
смотрим ОКВЭД этих компаний:

    улика есть + код в списке   — список работает, тут всё сошлось;
    улика есть + кода нет       — ВОТ ОНИ, пропущенные коды. Компания нужна нам по
                                  словам её собственного сайта, а мимо базы она
                                  прошла из-за строчки в реестре.

Отдельно считаем «сильную» улику — прямое слово «компрессор» или «пневмо» на
странице. Это ровно то, что владелец назвал «явно покупает компрессоры»: тут не
нужно ничего домысливать.

    python propushchennye_okvedy.py            сводка и топ пропущенных кодов
    python propushchennye_okvedy.py --spisok   коды списком, для правки карты
"""
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
import site_facts as SF           # noqa: E402
import enrich_db as EDB           # noqa: E402

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
# «явно покупает компрессоры» — прямое слово, без вывода по смежным признакам
_ПРЯМО = re.compile(r'компрессор|пневм|сжат\w+ воздух|воздушн\w+ ресивер', re.I)


def _цель(код):
    к = (код or '').split()[0] if код else ''
    while к:
        if к in EDB.OKVED_DIRECTIONS:
            return EDB.OKVED_DIRECTIONS[к]
        if '.' not in к:
            return None
        к = к.rsplit('.', 1)[0]
    return None


def собрать():
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    c.row_factory = sqlite3.Row
    строки = list(c.execute(
        "select f.inn, f.facts_json, coalesce(k.name,'') name, coalesce(k.okved,'') okved, "
        "coalesce(k.okved_all,'') okved_all, coalesce(k.division,'') division, "
        "coalesce(k.site,'') site, coalesce(k.is_competitor,'') konkurent "
        "from site_facts f join companies k on k.inn=f.inn "
        "where coalesce(f.facts_json,'')<>''"))
    c.close()
    из = []
    for r in строки:
        try:
            d = json.loads(r['facts_json'])
        except Exception:  # noqa: BLE001
            continue
        # у старых карточек разбора КЦ ещё нет — считаем его на лету тем же кодом
        разбор = d.get('разбор_КЦ') or SF.razlozhit_energohozyaystvo(d)
        улики = list(разбор.get('воздух_точно') or []) + list(разбор.get('газы_технические') or [])
        if not улики:
            continue
        из.append({'inn': str(r['inn']), 'name': r['name'], 'okved': r['okved'],
                   'okved_all': r['okved_all'], 'division': r['division'],
                   'site': r['site'], 'konkurent': str(r['konkurent'] or ''),
                   'улики': улики,
                   'прямо': any(_ПРЯМО.search(x) for x in улики)})
    return из


def сводка():
    сп = собрать()
    итог = {'паспортов_с_уликой_КЦ': len(сп),
            'из_них_прямо_компрессор_пневмо': sum(1 for x in сп if x['прямо']),
            'код_в_списке': 0, 'код_только_в_допах': 0, 'кода_нет_в_списке': 0,
            'без_оквэда_вовсе': 0}
    пропущено = defaultdict(lambda: {'компаний': 0, 'прямо': 0, 'примеры': []})
    for x in сп:
        if not x['okved'] and not x['okved_all']:
            итог['без_оквэда_вовсе'] += 1
            continue
        if _цель(x['okved']):
            итог['код_в_списке'] += 1
            continue
        if any(_цель(к) for к in (x['okved_all'] or '').split()):
            итог['код_только_в_допах'] += 1
            continue
        итог['кода_нет_в_списке'] += 1
        код = (x['okved'] or '?').split()[0]
        b = пропущено[код]
        b['компаний'] += 1
        b['прямо'] += 1 if x['прямо'] else 0
        if len(b['примеры']) < 3 and x['прямо']:
            b['примеры'].append({'имя': x['name'][:42], 'сайт': x['site'],
                                 'улика': x['улики'][0][:70]})
    верх = sorted(пропущено.items(), key=lambda kv: -kv[1]['прямо'])[:20]
    итог['название_кода'] = {}
    for код, _b in верх:
        for x in сп:
            if (x['okved'] or '').startswith(код):
                итог['название_кода'][код] = x['okved'][:60]
                break
    итог['пропущенные_коды'] = [{'код': к, **v} for к, v in верх]
    return итог


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    и = сводка()
    if '--spisok' in sys.argv:
        print(json.dumps([{'код': p['код'], 'название': и['название_кода'].get(p['код'], ''),
                           'компаний': p['компаний'], 'прямо': p['прямо']}
                          for p in и['пропущенные_коды']], ensure_ascii=False, indent=1))
        return 0
    коды = и.pop('пропущенные_коды')
    названия = и.pop('название_кода')
    print(json.dumps([{'код': p['код'], 'название': названия.get(p['код'], ''),
                       'компаний_с_уликой': p['компаний'], 'из_них_прямо': p['прямо'],
                       'примеры': p['примеры']} for p in коды[:12]],
                     ensure_ascii=False, indent=1))
    print(json.dumps(и, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
