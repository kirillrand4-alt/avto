# -*- coding: utf-8 -*-
"""Четыре явных конкурента из партии-935 — в стоп-лист панели по ИНН.

Сверка глазами 17.08 (все четверо сами производят/продают/чинят компрессоры,
МКС или генераторы азота — узкое определение владельца):
  7450061013 ЧЗМЭК                — МКС, генераторы азота, осушители
  3123133782 РЕМКОМПРЕССОР-СЕРВИС — продажа/ремонт/сервис компрессоров
  7806369727 АО НЗЛ               — центробежные/осевые компрессоры, ГПА
  7806151791 АО РЭПХ              — компрессорное оборудование, ГПА
Ставим через таблицу suppression (ai_quota и отправка её уважают); из группы
не выкидываем — стоп надёжнее и покрывает все группы сразу.
"""
import json
import sqlite3
import sys
import time

SENDER = r'C:\sender\sender.db'
ИННЫ = {'7450061013': 'ЧЗМЭК: МКС, генераторы азота',
        '3123133782': 'Ремкомпрессор-Сервис: продажа/ремонт компрессоров',
        '7806369727': 'НЗЛ: компрессоры, ГПА',
        '7806151791': 'РЭПХ: компрессорное оборудование, ГПА'}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    s = sqlite3.connect(SENDER, timeout=90)
    ts = time.strftime('%Y-%m-%dT%H:%M:%S')
    итог = {'добавлено': [], 'уже_были': []}
    with s:
        for инн, кто in ИННЫ.items():
            есть = s.execute("select 1 from suppression where scope='inn' "
                             'and value=?', (инн,)).fetchone()
            if есть:
                итог['уже_были'].append(инн)
                continue
            s.execute('insert into suppression(scope, value, reason, source, '
                      'created_at) values(?,?,?,?,?)',
                      ('inn', инн, 'competitor',
                       'enrich:is_competitor, сверка глазами 17.08 (%s)' % кто, ts))
            итог['добавлено'].append({'инн': инн, 'кто': кто})
    s.close()
    print(json.dumps(итог, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
