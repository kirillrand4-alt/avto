# -*- coding: utf-8 -*-
r"""Отделить новые сигналы от старых и выгрузить свежие в CSV.

Две разные «новизны», их нельзя путать:
  * `updated_at` — когда МЫ узнали (дата записи в базу). Заполнена всегда.
  * `ts` — когда событие произошло (дата источника). Пустая у большинства:
    vk, zakupki, dzen и xmlriver дату публикации не отдают.

Поэтому «новое» по умолчанию = «мы узнали недавно». Это честно и работает.
"""
import csv
import io
import json
import os
import sqlite3
import sys
import time

БАЗА = r'C:\sender\enrich.db'
DIR = r'C:\sender\server'


def main():
    дней = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    c = sqlite3.connect('file:%s?mode=ro' % БАЗА, uri=True, timeout=60)
    o = {}
    o['всего'] = c.execute('select count(*) from signals').fetchone()[0]
    o['по_дате_записи'] = c.execute(
        "select substr(updated_at,1,10) д, count(*) from signals "
        'group by 1 order by 1 desc limit 12').fetchall()
    o['с_датой_события'] = c.execute(
        "select count(*) from signals where ts like '20__-__-__%'").fetchone()[0]

    порог = time.strftime('%Y-%m-%d', time.localtime(time.time() - дней * 86400))
    строки = c.execute(
        "select s.inn, coalesce(cmp.name,''), s.source, s.event_type, s.what, "
        "coalesce(s.sum,''), s.hotness, s.source_url, substr(s.updated_at,1,16), "
        "coalesce(s.ts,''), coalesce(cmp.division,''), coalesce(cmp.region,'') "
        'from signals s left join companies cmp on cmp.inn = s.inn '
        'where substr(s.updated_at,1,10) >= ? order by s.hotness desc, s.rowid desc',
        (порог,)).fetchall()
    c.close()

    имя = 'signaly-novye-%s.csv' % time.strftime('%d%m')
    путь = os.path.join(DIR, имя)
    with io.open(путь, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['ИНН', 'компания', 'источник', 'тип события', 'что происходит',
                    'сумма', 'важность', 'ссылка', 'узнали', 'дата события',
                    'направление', 'регион'])
        for р in строки:
            w.writerow([str(x).replace('\n', ' ')[:400] for x in р])
        f.flush()
        os.fsync(f.fileno())
    try:
        import shutil
        shutil.copyfile(путь, os.path.join(r'C:\seostat\drop\drop-storage', имя))
    except Exception as e:  # noqa: BLE001
        o['дроп'] = repr(e)[:80]

    o['окно_дней'] = дней
    o['свежих_строк'] = len(строки)
    o['файл'] = имя
    print('===ИТОГ===')
    print(json.dumps(o, ensure_ascii=False, indent=1, default=str))


if __name__ == '__main__':
    main()
