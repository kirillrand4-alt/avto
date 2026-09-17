# -*- coding: utf-8 -*-
r"""Дотянуть слабые события: компания есть, а текст в разборе обрезан.

Замер 17.09: строк «без компании» в signals НЕТ вообще (событие без ИНН туда не
попадает), зато есть 81 строка вида «запуск нового объекта/цеха (текст обрезан)»
— компания и факт известны, конкретики нет. Это не мусор, а недобор: удалять
такое рано, сперва надо попробовать скачать статью и переразобрать.

Отличие от `dobor_teksta.py`: кандидаты берутся не из потока, а прямо из signals
по признакам обрезанного текста. Правила записи те же и такие же осторожные:
`what` меняется, только если новый длиннее старого на треть, `sum` — только в
пустое, ничего не удаляется. Результат сперва в jsonl с fsync, потом в базу.

Запуск: python dobor_slabyh.py [сколько]
"""
import io
import json
import os
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
os.chdir(DIR)
БАЗА = r'C:\sender\enrich.db'
ОТЧЁТ = os.path.join(DIR, 'dobor_slabyh.jsonl')

import news_scan as NS  # noqa: E402

ПРИЗНАКИ = ('текст обрезан', 'текст новости обрезан', 'подробности обрезаны',
            'конкретное действие не указано', 'конкретика отсутствует',
            'детали не указаны', 'детали не раскрыты', 'детали недоступны',
            'детали о проекте, этапе или инвестициях в тексте отсутствуют',
            'информация не раскрывается', 'уточните полный фрагмент',
            'направление не указано', 'объект инвестиций неизвестен')
_лок = threading.Lock()


def _записать(з):
    with _лок:
        with io.open(ОТЧЁТ, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
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
    c = sqlite3.connect('file:%s?mode=ro' % БАЗА, uri=True, timeout=60)
    строки = c.execute(
        "select inn, what, source_url, source, coalesce(sum,'') from signals "
        "where coalesce(source_url,'') like 'http%'").fetchall()
    c.close()
    вывод = []
    for inn, what, url, src, сум in строки:
        t = (what or '').lower()
        if not any(p in t for p in ПРИЗНАКИ) or url in сделано:
            continue
        вывод.append({'inn': str(inn), 'what': what, 'url': url,
                      'source': src, 'sum': сум})
        if len(вывод) >= предел:
            break
    return вывод


def обработать(d):
    з = {'url': d['url'], 'inn': d['inn'], 'было_what': (d['what'] or '')[:200],
         'было_sum': d['sum']}
    try:
        текст = NS._page_text(d['url'])
    except Exception as e:  # noqa: BLE001
        текст = ''
        з['ошибка'] = repr(e)[:80]
    if not текст:
        з['итог'] = 'не скачалось'
        _записать(з)
        return з
    з['знаков'] = len(текст)
    try:
        ev = NS.extract_event(текст[:NS.FULLTEXT_CAP], d.get('source') or '')
    except Exception as e:  # noqa: BLE001
        з['итог'] = 'ошибка классификатора: %r' % (e,)
        _записать(з)
        return з
    if not ev:
        з['итог'] = 'классификатор промолчал'
        _записать(з)
        return з
    з.update({'стало_what': (ev.get('what') or '')[:300], 'стало_sum': ev.get('sum') or '',
              'is_capex': ev.get('is_capex'), 'итог': 'разобрано'})
    _записать(з)
    return з


def обновить():
    правки = []
    with io.open(ОТЧЁТ, encoding='utf-8', errors='replace') as f:
        for s in f:
            try:
                з = json.loads(s)
            except Exception:  # noqa: BLE001
                continue
            if з.get('итог') != 'разобрано':
                continue
            ново = (з.get('стало_what') or '').strip()
            было = (з.get('было_what') or '').strip()
            м = {}
            if ново and len(ново) > len(было) * 1.3:
                м['what'] = ново
            if (з.get('стало_sum') or '').strip() and not (з.get('было_sum') or '').strip():
                м['sum'] = з['стало_sum']
            if м:
                правки.append((з['inn'], з['url'], м))
    if not правки:
        return {'правок': 0}
    c = sqlite3.connect(БАЗА, timeout=120)
    c.execute('pragma busy_timeout=120000')
    n = 0
    for inn, url, м in правки:
        поля = ', '.join('%s=?' % k for k in м)
        n += c.execute('update signals set %s where inn=? and source_url=?' % поля,
                       tuple(м.values()) + (inn, url)).rowcount
    c.commit()
    c.close()
    return {'правок': len(правки), 'обновлено_строк': n}


def main():
    предел = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    спис = кандидаты(предел)
    t0 = time.time()
    итоги = []
    if спис:
        with ThreadPoolExecutor(max_workers=6) as ex:
            итоги = list(ex.map(обработать, спис))
    свод = {}
    for з in итоги:
        свод[з.get('итог', '?')] = свод.get(з.get('итог', '?'), 0) + 1
    print('===ИТОГ===')
    print(json.dumps({'кандидатов': len(спис), 'минут': round((time.time() - t0) / 60, 1),
                      'по_итогам': свод, 'база': обновить()},
                     ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
