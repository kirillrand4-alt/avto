# -*- coding: utf-8 -*-
r"""Цикл паспортов ТОЛЬКО по мейеровским, у кого страницы уже скачаны.

Зачем отдельный: общий fakty_cikl направление не различает и в основном
перемалывает переразбор старых паспортов — за шесть часов мейеровских
прибавилось 56 штук при темпе разбора 3500 компаний в час. Здесь список
задаётся явно: те, у кого паспорта нет, а страницы есть.

Останавливается сам, когда список пуст.
"""
import json
import sqlite3
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import site_facts  # noqa: E402

БД = r'C:\sender\enrich.db'
ПАЧКА = 48
ПОТОКОВ = 8


def ждущие():
    c = sqlite3.connect('file:%s?mode=ro' % БД.replace('\\', '/'), uri=True, timeout=180)
    # sobrat ждёт записи с полями inn и site, а не голые ИНН: внутри зовётся
    # k['inn'] и k.get('site'). Список строк давал «'str' object has no
    # attribute 'get'» — тихо, каждый круг.
    ряды = [{'inn': str(r[0]), 'site': r[1] or ''} for r in c.execute(
        "select inn, coalesce(site, coalesce(cand_site,'')) from companies "
        "where coalesce(division,'') like '%meyer%' "
        "and not exists(select 1 from site_facts f where f.inn=companies.inn "
        "               and coalesce(f.facts_json,'')<>'') "
        "and exists(select 1 from stage_log s where s.inn=companies.inn "
        "           and s.stage in ('crawl','site'))")]
    c.close()
    return ряды


сделано = 0
while True:
    список = ждущие()
    print(time.strftime('%H:%M:%S'), 'ждут:', len(список), flush=True)
    if not список:
        print('очередь пуста, выхожу', flush=True)
        break
    кусок = список[:ПАЧКА]
    t0 = time.time()
    try:
        r = site_facts.sobrat(len(кусок), iz_kesha=True, spisok=кусок, potokov=ПОТОКОВ)
        r['сек'] = round(time.time() - t0)
        сделано += int(r.get('разобрано') or 0)
        r['всего_сделано'] = сделано
        print(time.strftime('%H:%M:%S'), json.dumps(r, ensure_ascii=False), flush=True)
        if not (r.get('разобрано') or r.get('без_страниц')):
            print('пачка не дала движения — пауза', flush=True)
            time.sleep(30)
    except Exception as e:  # noqa: BLE001
        print(time.strftime('%H:%M:%S'), 'сбой:', str(e)[:200], flush=True)
        time.sleep(20)
