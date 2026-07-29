# -*- coding: utf-8 -*-
"""Почему схема почты не вывелась ни у одной компании (способ А8).

Правило требует минимум ДВА адреса на своём домене, у которых известно ФИО
владельца. Ноль может значить и «таких компаний нет», и «разбор ФИО не
сходится с локальной частью». Разделяем: считаем воронку по шагам и, если
адреса с ФИО есть, показываем пары «локальная часть — ФИО», которые правило
НЕ распознало. По ним сразу видно, чего не хватает в наборе правил.
"""
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
import enrich_db as EDB          # noqa: E402
import enrich_contacts as EC     # noqa: E402
import email_schema as ES        # noqa: E402

e = EDB.EnrichDB().cx


def main():
    out = {}
    out['почт_всего'] = e.execute('select count(*) from emails').fetchone()[0]
    out['почт_с_ФИО'] = e.execute(
        "select count(*) from emails where ifnull(person,'')<>''").fetchone()[0]
    out['людей_с_почтой'] = e.execute(
        "select count(*) from people where ifnull(email,'')<>'' "
        "and ifnull(person,'')<>''").fetchone()[0]
    цели = [r[0] for r in e.execute(
        'select distinct inn from people where person<>"" '
        'and (email is null or email="")')]
    out['компаний_с_безадресными_людьми'] = len(цели)

    есть_сайт = свой = пар2 = 0
    не_распознано = []
    распознано = {}
    for inn in цели:
        дом = ES.свой_домен(inn)
        if not дом or дом in ES._ПУБЛИЧНЫЕ:
            continue
        есть_сайт += 1
        строки = list(e.execute(
            "select email, person from emails where inn=? and ifnull(person,'')<>''",
            (inn,)))
        строки += list(e.execute(
            "select email, person from people where inn=? and ifnull(email,'')<>'' "
            "and ifnull(person,'')<>''", (inn,)))
        свои = [(a.lower(), f) for a, f in строки
                if a and '@' in a and a.lower().endswith('@' + дом)]
        if свои:
            свой += 1
        if len(свои) >= 2:
            пар2 += 1
        for адрес, фио in свои:
            лок = адрес.split('@')[0]
            имя = ES.кандидаты(фио).get(лок)
            if имя:
                распознано[имя] = распознано.get(имя, 0) + 1
            elif len(не_распознано) < 20:
                не_распознано.append({'адрес': адрес, 'фио': фио, 'инн': inn})
    out['из_них_со_своим_доменом'] = есть_сайт
    out['есть_хоть_один_адрес_с_ФИО_на_своём_домене'] = свой
    out['есть_ДВА_и_больше'] = пар2
    out['правила_распознаны'] = распознано
    out['НЕ_распознанные_пары'] = не_распознано
    print(json.dumps(out, ensure_ascii=False, indent=1)[:5000])
    print(json.dumps({k: v for k, v in out.items()
                      if not isinstance(v, (list, dict))}, ensure_ascii=False))


if __name__ == '__main__':
    main()
