# -*- coding: utf-8 -*-
r"""Перелить реквизиты из базы обзвона в карточку компании.

Владелец 16.08 на моё «у 563 компаний с уликой нет ОКВЭДа, добираю через checko»:
«нету включая базу обзвона?». Проверил — и он прав: у ВСЕХ 1386 компаний, где в
enrich.db кода нет, он лежит в obzvon-index.db в поле okved_main. Сто процентов.

То есть добор через checko+dadata для них был лишней тратой: реестровые реквизиты
у нас уже есть, просто в другой таблице. Внешние источники нужны там, где своих
данных НЕТ, — а не там, где их не посмотрели.

Второй заход 17.08. Владелец на мою фразу «выручка есть только у 1461 компании»:
«выручка есть у всех в базе обзвона, опять смотришь не полные данные». Проверил —
у 27399 компаний, где у нас пусто, выручка в обзвоне заполнена. Та же история, что
с ОКВЭД, и она повторилась ровно потому, что первый добор я сделал узким: взял
четыре поля вместо всех, какие есть.

Поэтому теперь берём всё, что относится к самой компании: финансы (выручка,
прибыль, капитал, год отчётности, ПХР), реестровое (ОГРН, КПП, ОПФ, статус,
адрес, директор), полный список ОКВЭД и расчёт владельца по оборудованию.
Контакты (phones_base, emails_base) СЮДА НЕ ТЯНЕМ: почта уходит в рассылку и
обязана пройти нашу проверку на скрытые адреса и ловушки, а не появляться в
карточке в обход неё.

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
    # берём ВСЕХ: добор ставит только в пустые поля, а узкая выборка и была
    # причиной того, что выручку не забрали в первый раз
    return [str(r[0]) for r in c.execute('select inn from companies')]


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
                "coalesce(region,'') region, coalesce(revenue_rub,'') revenue_rub, "
                "coalesce(god_otch,'') god, coalesce(pxr,'') pxr, coalesce(kpp,'') kpp, "
                "coalesce(opf,'') opf, coalesce(status,'') status, "
                "coalesce(address,'') address, coalesce(director,'') director, "
                "coalesce(okved_all_codes,'') okved_all, "
                "coalesce(equip_categories,'') equip, "
                "coalesce(priority_total,'') prio_total, coalesce(priority_max,'') prio_max "
                "from obzvon where inn in (%s)" % q, часть):
            если = dict(r)
            если['name'] = (если['nf'] or если['ns'] or '').strip()
            если['short_name'] = (если['ns'] or '').strip()
            из.append(если)
    o.close()
    return из


ПОЛЯ = (('okved', 'okved'), ('name', 'name'), ('short_name', 'short_name'),
        ('ogrn', 'ogrn'), ('region', 'region'), ('revenue_rub', 'revenue_rub'),
        ('revenue_year', 'god'), ('pxr', 'pxr'), ('kpp', 'kpp'), ('opf', 'opf'),
        ('status_egrul', 'status'), ('address', 'address'), ('director', 'director'),
        ('okved_all', 'okved_all'), ('oborudovanie_po_okved', 'equip'),
        ('priority_total', 'prio_total'), ('priority_max', 'prio_max'))


def применить():
    строки = собрать()
    c = sqlite3.connect(BD, timeout=60)
    for колонка in ('kpp TEXT', 'opf TEXT', 'status_egrul TEXT', 'address TEXT',
                    'oborudovanie_po_okved TEXT', 'priority_total TEXT',
                    'priority_max TEXT'):
        try:
            c.execute('ALTER TABLE companies ADD COLUMN %s' % колонка)
        except Exception:  # noqa: BLE001
            pass
    итог = {'нашли_в_обзвоне': len(строки)}
    for r in строки:
        for колонка, ключ in ПОЛЯ:
            зн = str(r.get(ключ) or '').strip()
            if not зн:
                continue
            n = c.execute(
                "UPDATE companies SET %s=?, updated_at=? WHERE inn=? "
                "AND coalesce(%s,'')=''" % (колонка, колонка),
                (зн[:300], time.strftime('%Y-%m-%dT%H:%M:%S'), str(r['inn']))).rowcount
            if n:
                итог[колонка] = итог.get(колонка, 0) + n
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
                          'из_них_с_выручкой': sum(1 for r in строки if r['revenue_rub']),
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
