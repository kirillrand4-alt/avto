# -*- coding: utf-8 -*-
r"""Вернуть в разбор карточки, выбывшие не по своей вине.

Владелец 17.08, глядя на журнал шлюза со стеной «upstream provider is temporarily
unavailable» по gpt-5.6-luna: «а вот это потом переспросится? то что 1 модель
спать ушла, когда проснётся».

Не переспрашивалось. Счётчик popytok не различал, почему карточка не собралась:
три круга при лежащем шлюзе — и компания выбывала из разбора навсегда, хотя
виноват был не её сайт. То же самое со «страниц в кэше нет»: обход привезёт
страницы позже, а карточка уже закрыта.

Само правило починено в site_facts (за чужую вину попытка не списывается, работа
откладывается). Здесь — разовая разморозка тех, кто уже выбыл.

    python razmorozka.py --stat
    python razmorozka.py --primenit
"""
import json
import os
import sqlite3
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
import site_facts as SF          # noqa: E402

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
ЛОГ = os.path.join(DIR, 'razmorozka.jsonl')


def найти():
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    c.row_factory = sqlite3.Row
    строки = list(c.execute(
        "select inn, coalesce(note,'') note, coalesce(popytok,0) popytok "
        "from site_facts where coalesce(facts_json,'')='' and coalesce(popytok,0) >= 3"))
    c.close()
    из = []
    for r in строки:
        чья = SF._ne_nasha_vina(r['note'])
        if чья:
            из.append({'inn': str(r['inn']), 'note': r['note'][:90], 'вина': чья,
                       'popytok': r['popytok']})
    return из


def применить():
    находки = найти()
    SF._bd().close()          # миграции колонок живут там; своим connect их не создать
    c = sqlite3.connect(BD, timeout=60)
    n = 0
    for f in находки:
        n += c.execute("UPDATE site_facts SET popytok=0, otlozheno_do=0 WHERE inn=?",
                       (f['inn'],)).rowcount
    c.commit()
    c.close()
    with open(ЛОГ, 'a', encoding='utf-8') as fl:
        for f in находки:
            fl.write(json.dumps(f, ensure_ascii=False) + '\n')
        fl.flush()
        os.fsync(fl.fileno())
    return {'разморожено': n, 'по_вине': {в: sum(1 for f in находки if f['вина'] == в)
                                          for в in ('провайдер', 'страницы')}}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    a = sys.argv[1:]
    if not a or a[0] == '--stat':
        н = найти()
        print(json.dumps({'выбыли_не_по_своей_вине': len(н),
                          'по_вине': {в: sum(1 for f in н if f['вина'] == в)
                                      for в in ('провайдер', 'страницы')},
                          'примеры': н[:6]}, ensure_ascii=False, indent=1))
    elif a[0] == '--primenit':
        print(json.dumps(применить(), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
