# -*- coding: utf-8 -*-
r"""Перелить реквизиты из базы обзвона: имя, ОГРН, ОКВЭД, регион.

Владелец 16.08 на моё «у 563 компаний с уликой нет ОКВЭДа, добираю через checko»:
«нету включая базу обзвона?». Проверил — и он прав: у ВСЕХ 1386 компаний, где в
enrich.db кода нет, он лежит в obzvon-index.db в поле okved_main. Сто процентов.

То есть добор через checko+dadata для них был лишней тратой: реестровые реквизиты
у нас уже есть, просто в другой таблице. Внешние источники нужны там, где своих
данных НЕТ, — а не там, где их не посмотрели.

Ставим только в пустые поля: свои данные в companies (например, уточнённый ОКВЭД
из checko) не затираем.

    python okved_iz_obzvona.py --stat
    python okved_iz_obzvona.py --primenit
"""
import json
import os
import sqlite3
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
OBZVON = r'C:\sender\obzvon-index.db'
ЛОГ = os.path.join(DIR, 'okved_iz_obzvona.jsonl')


def _нужны(c):
    return [str(r[0]) for r in c.execute(
        "select inn from companies where coalesce(okved,'')='' or coalesce(name,'')=''")]


def собрать():
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    нужны = _нужны(c)
    c.close()
    if not нужны:
        return []
    o = sqlite3.connect(OBZVON)
    o.row_factory = sqlite3.Row
    из = []
    for i in range(0, len(нужны), 400):
        часть = нужны[i:i + 400]
        q = ','.join('?' * len(часть))
        for r in o.execute(
                "select inn, coalesce(okved_main,'') okved, coalesce(name_full,'') nf, "
                "coalesce(name_short,'') ns, coalesce(ogrn,'') ogrn, "
                "coalesce(region,'') region from obzvon where inn in (%s)" % q, часть):
            если = dict(r)
            если['name'] = (если['nf'] or если['ns'] or '').strip()
            if если['okved'] or если['name']:
                из.append(если)
    o.close()
    return из


def применить():
    строки = собрать()
    c = sqlite3.connect(BD, timeout=60)
    итог = {'нашли_в_обзвоне': len(строки), 'проставлен_оквэд': 0, 'проставлено_имя': 0,
            'проставлен_огрн': 0, 'проставлен_регион': 0}
    for r in строки:
        итог['проставлен_оквэд'] += c.execute(
            "UPDATE companies SET okved=?, istochnik_rekvizitov='обзвон', updated_at=? "
            "WHERE inn=? AND coalesce(okved,'')='' AND ?<>''",
            (r['okved'], time.strftime('%Y-%m-%dT%H:%M:%S'), str(r['inn']),
             r['okved'])).rowcount
        итог['проставлено_имя'] += c.execute(
            "UPDATE companies SET name=? WHERE inn=? AND coalesce(name,'')='' AND ?<>''",
            (r['name'][:200], str(r['inn']), r['name'])).rowcount
        итог['проставлен_огрн'] += c.execute(
            "UPDATE companies SET ogrn=? WHERE inn=? AND coalesce(ogrn,'')='' AND ?<>''",
            (r['ogrn'], str(r['inn']), r['ogrn'])).rowcount
        итог['проставлен_регион'] += c.execute(
            "UPDATE companies SET region=? WHERE inn=? AND coalesce(region,'')='' AND ?<>''",
            (r['region'], str(r['inn']), r['region'])).rowcount
    c.commit()
    c.close()
    with open(ЛОГ, 'a', encoding='utf-8') as f:
        for r in строки:
            f.write(json.dumps({'inn': str(r['inn']), 'okved': r['okved'],
                                'name': r['name'][:60]}, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    return итог


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    a = sys.argv[1:]
    if not a or a[0] == '--stat':
        строки = собрать()
        print(json.dumps({'кому_нужны_реквизиты': len(строки),
                          'из_них_с_оквэдом': sum(1 for r in строки if r['okved']),
                          'примеры': [{'инн': str(r['inn']), 'оквэд': r['okved'][:50],
                                       'имя': r['name'][:40]} for r in строки[:6]]},
                         ensure_ascii=False, indent=1))
    elif a[0] == '--primenit':
        print(json.dumps(применить(), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
