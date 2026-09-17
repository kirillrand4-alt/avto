# -*- coding: utf-8 -*-
r"""Отобрать события, после которых реально нужен компрессор от 90 кВт.

Владелец 17.09: «почистим события от тех, в результате создания чего не нужен
будет компрессор на 90 кВт и выше».

Важная оговорка, заложенная в критерий: у Руспрома ДВЕ линии. Под компрессор
90 кВт мейеровские поводы (зерно, пищевая сортировка, рентген-инспекция) не
подходят, но это наш второй бизнес — поэтому событие помечается двумя флагами
и удаляется, только если не подходит НИ ПОД ОДНУ линию.

Скорость: события идут в модель пачками по 20 в 12 потоков, то есть 4 тысячи
событий — это около двух сотен вызовов, а не четыре тысячи.

Durable: вердикты пишутся в otbor_90kvt.jsonl с fsync ДО любой правки базы,
повторный запуск продолжает с места остановки.

Запуск: python otbor_90kvt.py [--udalit]   (без флага — только разметка)
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
ОТЧЁТ = os.path.join(DIR, 'otbor_90kvt.jsonl')
ПАЧКА = 20

sys.path.insert(0, r'C:\sender')
import verify_company as VC  # noqa: E402

ПРОМПТ = (
    'Ты отбираешь промышленные события для поставщика двух линий оборудования.\n'
    'Линия А: компрессорные станции мощностью ОТ 90 кВт, генераторы азота и кислорода '
    'промышленного масштаба.\n'
    'Линия Б: фотосепараторы и рентген-инспекция для зерна, пищевой переработки, '
    'сортировки сырья и вторсырья.\n\n'
    'Для КАЖДОГО события верни {"i":номер,"a":true/false,"b":true/false}.\n'
    'a=true, если после этого события компании с высокой вероятностью понадобится '
    'компрессор ОТ 90 кВт или генератор газов сопоставимого масштаба: металлургия, '
    'химия и нефтехимия, нефтегаз и добыча, машиностроение, цемент и стройматериалы, '
    'стекло, ЦБК и деревообработка, крупные пищевые и фармацевтические заводы, '
    'обогатительные фабрики, крупные литейные и гальванические производства, '
    'компрессорные и азотные станции как таковые.\n'
    'a=false, если масштаб или тип объекта этого не требует: склады и логистика без '
    'производства, торговые и офисные объекты, жильё, дороги, соцобъекты, малые '
    'мастерские и сборочные участки, дата-центры, гостиницы, фермы без переработки, '
    'ремонт зданий, благоустройство.\n'
    'b=true, если событие про зерно, пищевую переработку, сортировку сырья или '
    'вторсырья, где применимы фотосепараторы или рентген-инспекция.\n'
    'Ответ — ТОЛЬКО JSON-массив объектов, без markdown и пояснений.\n\n'
    'События:\n')

_лок = threading.Lock()


def _записать(записи):
    with _лок:
        with io.open(ОТЧЁТ, 'a', encoding='utf-8') as f:
            for з in записи:
                f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def кандидаты():
    сделано = set()
    if os.path.exists(ОТЧЁТ):
        with io.open(ОТЧЁТ, encoding='utf-8', errors='replace') as f:
            for s in f:
                try:
                    з = json.loads(s)
                    сделано.add((str(з['inn']), з['url']))
                except Exception:  # noqa: BLE001
                    pass
    c = sqlite3.connect('file:%s?mode=ro' % БАЗА, uri=True, timeout=60)
    строки = c.execute(
        "select s.inn, coalesce(s.source_url,''), s.event_type, s.what, "
        "coalesce(cmp.name,''), coalesce(cmp.division,'') from signals s "
        'left join companies cmp on cmp.inn=s.inn').fetchall()
    c.close()
    return [{'inn': str(r[0]), 'url': r[1], 'тип': r[2], 'что': (r[3] or '')[:260],
             'имя': r[4][:60], 'напр': r[5]}
            for r in строки if (str(r[0]), r[1]) not in сделано]


def пачка(куски):
    текст = ПРОМПТ + '\n'.join(
        '%d. [%s] %s — %s' % (i, д['тип'], д['имя'], д['что'])
        for i, д in enumerate(куски))
    try:
        out = VC._provider_call_stdlib(текст)
    except Exception as e:  # noqa: BLE001
        _записать([{**д, 'ошибка': repr(e)[:80]} for д in куски])
        return 0
    import re
    m = re.search(r'\[.*\]', out or '', re.S)
    if not m:
        _записать([{**д, 'ошибка': 'модель не вернула JSON'} for д in куски])
        return 0
    try:
        ответы = json.loads(m.group(0))
    except Exception as e:  # noqa: BLE001
        _записать([{**д, 'ошибка': 'битый JSON: %r' % (e,)} for д in куски])
        return 0
    по_номеру = {int(о.get('i', -1)): о for о in ответы if isinstance(о, dict)}
    записи = []
    for i, д in enumerate(куски):
        о = по_номеру.get(i)
        if о is None:
            записи.append({**д, 'ошибка': 'нет ответа по номеру'})
        else:
            записи.append({'inn': д['inn'], 'url': д['url'], 'тип': д['тип'],
                           'имя': д['имя'], 'что': д['что'][:120],
                           'a': bool(о.get('a')), 'b': bool(о.get('b'))})
    _записать(записи)
    return len(записи)


def удалить():
    """Снести то, что не подходит ни под одну линию. С бэкапом."""
    пары = []
    with io.open(ОТЧЁТ, encoding='utf-8', errors='replace') as f:
        for s in f:
            try:
                з = json.loads(s)
            except Exception:  # noqa: BLE001
                continue
            if з.get('ошибка') or 'a' not in з:
                continue
            if not з['a'] and not з['b']:
                пары.append((str(з['inn']), з['url']))
    if not пары:
        return {'к_удалению': 0}
    c = sqlite3.connect(БАЗА, timeout=120)
    c.execute('pragma busy_timeout=120000')
    бэк = os.path.join(DIR, 'udalyonnye-ne-nash-profil-%s.jsonl' % time.strftime('%d%m-%H%M'))
    сохранено = 0
    with io.open(бэк, 'w', encoding='utf-8') as f:
        for inn, url in пары:
            for р in c.execute(
                    "select inn, source, event_type, what, coalesce(sum,''), hotness, "
                    'source_url, updated_at from signals where inn=? and source_url=?',
                    (inn, url)):
                f.write(json.dumps({'inn': р[0], 'источник': р[1], 'тип': р[2],
                                    'что': р[3], 'сумма': р[4], 'важность': р[5],
                                    'ссылка': р[6], 'узнали': р[7]},
                                   ensure_ascii=False) + '\n')
                сохранено += 1
        f.flush()
        os.fsync(f.fileno())
    try:
        import shutil
        shutil.copyfile(бэк, os.path.join(r'C:\seostat\drop\drop-storage',
                                          os.path.basename(бэк)))
    except Exception:  # noqa: BLE001
        pass
    было = c.execute('select count(*) from signals').fetchone()[0]
    n = 0
    for inn, url in пары:
        n += c.execute('delete from signals where inn=? and source_url=?',
                       (inn, url)).rowcount
    c.commit()
    стало = c.execute('select count(*) from signals').fetchone()[0]
    c.close()
    return {'к_удалению': len(пары), 'в_бэкапе': сохранено, 'удалено': n,
            'было': было, 'стало': стало, 'бэкап': os.path.basename(бэк)}


def main():
    спис = кандидаты()
    пачки = [спис[i:i + ПАЧКА] for i in range(0, len(спис), ПАЧКА)]
    t0 = time.time()
    if пачки:
        with ThreadPoolExecutor(max_workers=12) as ex:
            list(ex.map(пачка, пачки))
    свод = {'a_да': 0, 'b_да': 0, 'ни_то_ни_то': 0, 'ошибок': 0}
    with io.open(ОТЧЁТ, encoding='utf-8', errors='replace') as f:
        for s in f:
            try:
                з = json.loads(s)
            except Exception:  # noqa: BLE001
                continue
            if з.get('ошибка'):
                свод['ошибок'] += 1
            elif з.get('a'):
                свод['a_да'] += 1
            elif з.get('b'):
                свод['b_да'] += 1
            else:
                свод['ни_то_ни_то'] += 1
    итог = {'событий': len(спис), 'пачек': len(пачки),
            'минут': round((time.time() - t0) / 60, 1), 'разметка': свод}
    if '--udalit' in sys.argv:
        итог['чистка'] = удалить()
    print('===ИТОГ===')
    print(json.dumps(итог, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
