# -*- coding: utf-8 -*-
"""Файлы Ростехнадзора, найденные поиском ЛПР, — в поток графиков.

Поиск людей по должностям (`lpr_serp`) обходится дорого: двадцать запросов к
выдаче на компанию. Но лучшие его находки — это ссылки на графики РТН, причём
по путям, которых в нашем потоке нет: разведка ходила в
`/activity/attestation/schedule_chlb/`, а выдача принесла
`/activity/attestation/shedule/` (без «c» — так у них написано) и
`/activity/proverka znaniy/`.

Значит платить за классификацию этих страниц незачем: у нас уже есть разбор
графиков, который вытащит из файла не одного человека из сниппета, а всю
таблицу. Забираем из пачек только ссылки на документы gosnadzor и кладём их в
`rtn_files.jsonl` — дальше штатные `собрать` и `свести`.

Запуск: python rtn_iz_vydachi.py [--apply]
"""
import gzip
import io
import json
import os
import re
import sys
import urllib.parse
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\server\ops')
import rtn_znaniya as RTN  # noqa: E402

ХРАН = r'C:\seostat\drop\drop-storage'
ПРИМЕНИТЬ = '--apply' in sys.argv
_ФАЙЛ = re.compile(r'\.(docx?|xlsx?|pdf)(\?|$)', re.I)


def _читать(путь):
    сыр = open(путь, 'rb').read()
    if сыр[:2] == b'\x1f\x8b':
        сыр = gzip.decompress(сыр)
    return json.loads(сыр.decode('utf-8', 'replace'))


def main():
    пачки = [f for f in os.listdir(ХРАН)
             if f.startswith('lpr_batch_') and f.endswith(('.json', '.json.gz'))]
    урлы = {}
    итог = Counter()
    for имя in пачки:
        try:
            d = _читать(os.path.join(ХРАН, имя))
        except Exception as e:  # noqa: BLE001
            итог[f'пачка не прочиталась: {str(e)[:40]}'] += 1
            continue
        записи = d if isinstance(d, list) else (d.get('люди') or [])
        итог['пачек прочитано'] += 1
        for з in записи:
            for стр in (з.get('страницы') or []):
                у = (стр.get('url') or '').strip()
                if not у or 'gosnadzor' not in у.lower():
                    continue
                итог['ссылок gosnadzor'] += 1
                if not _ФАЙЛ.search(у):
                    итог['не файл (страница)'] += 1
                    continue
                урлы[у] = стр.get('дата') or ''

    было = set()
    if os.path.exists(RTN.П_ССЫЛКИ):
        for ln in io.open(RTN.П_ССЫЛКИ, encoding='utf-8', errors='replace'):
            try:
                было.add(json.loads(ln).get('url'))
            except Exception:  # noqa: BLE001
                continue
    новые = {у: д for у, д in урлы.items() if у not in было}

    # путь, по которому файл лежит, — полезная подсказка для будущей разведки
    пути = Counter()
    for у in новые:
        ч = urllib.parse.urlparse(у)
        пути[ч.netloc + '/'.join(ч.path.split('/')[:4])] += 1

    if ПРИМЕНИТЬ and новые:
        with io.open(RTN.П_ССЫЛКИ, 'a', encoding='utf-8') as ф:
            for у, д in новые.items():
                ф.write(json.dumps({'url': у, 'дата': д or RTN.дата_из_имени(у),
                                    'откуда': 'поиск ЛПР'},
                                   ensure_ascii=False) + '\n')
            ф.flush()
            os.fsync(ф.fileno())

    print(json.dumps({
        'пачек': len(пачки), 'разбор': итог.most_common(),
        'файлов_gosnadzor_всего': len(урлы),
        'из_них_НОВЫХ': len(новые),
        'было_в_потоке': len(было),
        'частые_пути': пути.most_common(8),
        'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой (--apply)',
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
