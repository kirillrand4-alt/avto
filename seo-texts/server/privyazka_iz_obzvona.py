# -*- coding: utf-8 -*-
r"""Вернуть компаниям сайт из базы обзвона там, где привязки нет.

Нашлось при разборе кэша 16.08. После чистки площадок 659 компаний остались вовсе
без адреса — и у 579 из них сайт всё это время лежал в базе обзвона. То есть мы
обходили check.tochka.com и trade.bashkortostan.ru, имея у себя настоящий адрес.

Примеры из выборки: ИНН 0220025748 — в обзвоне kosmeta-kazan.ru, а в кэше страницы
elkar.ru; ИНН 0245972331 — в обзвоне metall-tochka.ru, в кэше портал
trade.bashkortostan.ru.

Из строки обзвона берём ПЕРВЫЙ адрес, который не площадка: там встречаются
«https://vk.com/club201201415 | https://wa.me/...» — это не сайт предприятия.

Ставим в companies.site с пометкой site_source='обзвон'. Это не «подтверждённая»
привязка: реестровая выгрузка — источник хороший, но проверка всё равно впереди,
её сделает обычный обход (ИНН или имя на странице).

    python privyazka_iz_obzvona.py --stat
    python privyazka_iz_obzvona.py --primenit
"""
import json
import os
import re
import sqlite3
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
import ploshchadki as PL          # noqa: E402

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
OBZVON = r'C:\sender\obzvon-index.db'
ЛОГ = os.path.join(DIR, 'privyazka_iz_obzvona.jsonl')


def первый_годный(строка):
    """Первый адрес из «a | b | c», который не площадка и похож на сайт."""
    for кусок in re.split(r'[|,;\s]+', строка or ''):
        к = кусок.strip()
        if not к or '.' not in к:
            continue
        if not re.match(r'^(https?://)?[\w.-]+\.[a-zа-я]{2,}', к, re.I):
            continue
        if PL.из_списка(к):
            continue
        return re.sub(r'^https?://', '', к).rstrip('/')
    return ''


def найти():
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    без_сайта = [str(r[0]) for r in c.execute(
        "select inn from companies where coalesce(site,'')='' and coalesce(cand_site,'')=''")]
    c.close()
    if not без_сайта:
        return []
    o = sqlite3.connect(OBZVON)
    найдено = []
    for i in range(0, len(без_сайта), 400):
        часть = без_сайта[i:i + 400]
        q = ','.join('?' * len(часть))
        for inn, sites in o.execute(
                "select inn, coalesce(sites,'') from obzvon where inn in (%s)" % q, часть):
            u = первый_годный(sites)
            if u:
                найдено.append({'inn': str(inn), 'site': u, 'исходно': (sites or '')[:80]})
    o.close()
    return найдено


def применить():
    найдено = найти()
    c = sqlite3.connect(BD, timeout=60)
    поставлено = 0
    for н in найдено:
        поставлено += c.execute(
            "UPDATE companies SET site=?, site_source='обзвон', updated_at=? "
            "WHERE inn=? AND coalesce(site,'')='' AND coalesce(cand_site,'')=''",
            (н['site'], time.strftime('%Y-%m-%dT%H:%M:%S'), н['inn'])).rowcount
    c.commit()
    c.close()
    with open(ЛОГ, 'a', encoding='utf-8') as f:
        for н in найдено:
            f.write(json.dumps(н, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    return {'нашли_в_обзвоне': len(найдено), 'поставлено': поставлено}


def main():
    a = sys.argv[1:]
    if not a or a[0] == '--stat':
        найдено = найти()
        print(json.dumps({'нашли_в_обзвоне': len(найдено), 'примеры': найдено[:10]},
                         ensure_ascii=False, indent=1))
    elif a[0] == '--primenit':
        print(json.dumps(применить(), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
