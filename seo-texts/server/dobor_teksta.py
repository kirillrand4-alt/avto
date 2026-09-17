# -*- coding: utf-8 -*-
r"""Перекачать статьи для событий, классифицированных по одному заголовку.

Замер 17.09: из 1 912 событий с телеметрией длины у 292 текст не скачался вовсе
(`article_chars: 0`), и классификатор судил по заголовку. Заголовок не содержит
конкретики про линии и мощности — ровно того, ради чего полный текст и качается.

Что делает скрипт: находит такие события в потоке, качает статью заново,
переклассифицирует полным текстом через того же `extract_event` и обновляет в
signals поля `what` и `sum` — но ТОЛЬКО если новое содержательнее старого.

Осторожность по данным:
  * событие ищется по паре (ИНН, ссылка) — чужую строку не тронем;
  * `what` заменяется, только если новый текст длиннее старого на треть;
  * `sum` заполняется, только если старое пустое;
  * если классификатор теперь говорит `is_capex=false`, строку НЕ удаляем —
    только помечаем в отчёте, решение за владельцем;
  * каждый результат пишется в `dobor_teksta.jsonl` с fsync ДО записи в базу,
    поэтому занятая база работу не съедает.

Резюмируемость: уже обработанные ссылки берутся из того же jsonl.

Запуск: python dobor_teksta.py [сколько_максимум]
"""
import io
import json
import os
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
os.chdir(DIR)
БАЗА = r'C:\sender\enrich.db'
ПОТОК = os.path.join(DIR, 'news_stream.jsonl')
ОТЧЁТ = os.path.join(DIR, 'dobor_teksta.jsonl')

import news_scan as NS  # noqa: E402

_лок = __import__('threading').Lock()


def _записать(зап):
    with _лок:
        with io.open(ОТЧЁТ, 'a', encoding='utf-8') as f:
            f.write(json.dumps(зап, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def кандидаты(предел):
    сделано = set()
    if os.path.exists(ОТЧЁТ):
        with io.open(ОТЧЁТ, encoding='utf-8', errors='replace') as f:
            for s in f:
                try:
                    сделано.add(json.loads(s).get('url'))
                except Exception:  # noqa: BLE001
                    pass
    вывод = []
    with io.open(ПОТОК, encoding='utf-8', errors='replace') as f:
        for s in f:
            if '"article_chars"' not in s:
                continue
            try:
                d = json.loads(s)
            except Exception:  # noqa: BLE001
                continue
            if int(d.get('article_chars') or 0):
                continue
            url = (d.get('source_url') or d.get('link') or '').strip()
            if not url.startswith('http') or url in сделано:
                continue
            вывод.append(d)
            if len(вывод) >= предел:
                break
    return вывод


def обработать(d):
    url = (d.get('source_url') or d.get('link') or '').strip()
    старое_what = (d.get('what') or '').strip()
    старое_sum = (d.get('sum') or '').strip()
    зап = {'url': url, 'inn': d.get('inn'), 'компания': d.get('company'),
           'было_what': старое_what[:200], 'было_sum': старое_sum}
    try:
        текст = NS._page_text(url)
    except Exception as e:  # noqa: BLE001
        текст = ''
        зап['ошибка_загрузки'] = repr(e)[:90]
    if not текст:
        зап['итог'] = 'снова не скачалось'
        _записать(зап)
        return зап
    зап['знаков'] = len(текст)
    полный = (str(d.get('title') or '') + '\n\n' + текст)[:NS.FULLTEXT_CAP]
    try:
        ev = NS.extract_event(полный, d.get('source') or '')
    except Exception as e:  # noqa: BLE001
        зап['итог'] = 'ошибка классификатора: %r' % (e,)
        _записать(зап)
        return зап
    if not ev:
        зап['итог'] = 'классификатор промолчал'
        _записать(зап)
        return зап
    зап['стало_what'] = (ev.get('what') or '')[:300]
    зап['стало_sum'] = ev.get('sum') or ''
    зап['is_capex'] = ev.get('is_capex')
    зап['компания_новая'] = ev.get('company')
    зап['итог'] = 'разобрано'
    _записать(зап)
    return зап


def обновить_базу():
    """Перенести накопленное из отчёта в signals. Отдельным шагом — чтобы
    занятая база не мешала самой перекачке."""
    правки = []
    with io.open(ОТЧЁТ, encoding='utf-8', errors='replace') as f:
        for s in f:
            try:
                з = json.loads(s)
            except Exception:  # noqa: BLE001
                continue
            if з.get('итог') != 'разобрано' or not з.get('inn'):
                continue
            ново = (з.get('стало_what') or '').strip()
            было = (з.get('было_what') or '').strip()
            нов_сум = (з.get('стало_sum') or '').strip()
            что_менять = {}
            if ново and len(ново) > len(было) * 1.3:
                что_менять['what'] = ново
            if нов_сум and not (з.get('было_sum') or '').strip():
                что_менять['sum'] = нов_сум
            if что_менять:
                правки.append((з['inn'], з['url'], что_менять))
    if not правки:
        return {'правок': 0}
    c = sqlite3.connect(БАЗА, timeout=120)
    c.execute('pragma busy_timeout=120000')
    обновлено = 0
    for inn, url, м in правки:
        поля = ', '.join('%s=?' % k for k in м)
        cur = c.execute('update signals set %s where inn=? and source_url=?' % поля,
                        tuple(м.values()) + (str(inn), url))
        обновлено += cur.rowcount
    c.commit()
    c.close()
    return {'правок_подготовлено': len(правки), 'строк_обновлено': обновлено}


def main():
    предел = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    спис = кандидаты(предел)
    t0 = time.time()
    итоги = []
    if спис:
        with ThreadPoolExecutor(max_workers=6) as ex:
            итоги = list(ex.map(обработать, спис))
    свод = {}
    for з in итоги:
        свод[з.get('итог', '?')] = свод.get(з.get('итог', '?'), 0) + 1
    база = обновить_базу()
    print('===ИТОГ===')
    print(json.dumps({'кандидатов': len(спис), 'минут': round((time.time() - t0) / 60, 1),
                      'по_итогам': свод, 'база': база,
                      'стало_не_капекс': sum(1 for з in итоги if з.get('is_capex') is False)},
                     ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
