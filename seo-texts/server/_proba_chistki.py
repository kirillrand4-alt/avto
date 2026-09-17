# -*- coding: utf-8 -*-
r"""Удалить из signals события, которые на ПОЛНОМ тексте оказались не капексом.

Владелец 17.09: «те 18 которые не капекс — удали, нам нужна база без мусора».

Порядок намеренно такой: сперва выгрузка удаляемых строк в файл рядом с базой
(и копия на дроп), потом удаление. Удаление из боевой базы необратимо, а файл
позволяет вернуть строку одной вставкой, если окажется, что классификатор
ошибся на конкретной новости.

Строки ищутся по паре (ИНН, ссылка) — ровно те, что перекачивались.
Запуск: python chistka_ne_kapeks.py [--proba]
"""
import io
import json
import os
import sqlite3
import sys
import time

DIR = r'C:\sender\server'
БАЗА = r'C:\sender\enrich.db'
ОТЧЁТ = os.path.join(DIR, 'dobor_teksta.jsonl')


def main():
    проба = True
    пары = []
    with io.open(ОТЧЁТ, encoding='utf-8', errors='replace') as f:
        for s in f:
            try:
                з = json.loads(s)
            except Exception:  # noqa: BLE001
                continue
            if з.get('is_capex') is False and з.get('inn') and з.get('url'):
                пары.append((str(з['inn']), з['url'], з.get('компания') or ''))

    c = sqlite3.connect(БАЗА, timeout=120)
    c.execute('pragma busy_timeout=120000')
    к_удалению = []
    for inn, url, имя in пары:
        for р in c.execute(
                'select inn, source, event_type, what, coalesce(sum,\'\'), hotness, '
                'source_url, updated_at, coalesce(ts,\'\') from signals '
                'where inn=? and source_url=?', (inn, url)).fetchall():
            к_удалению.append({'inn': р[0], 'источник': р[1], 'тип': р[2], 'что': р[3],
                               'сумма': р[4], 'важность': р[5], 'ссылка': р[6],
                               'узнали': р[7], 'дата_события': р[8], 'компания': имя})

    итог = {'помечено_не_капекс': len(пары), 'найдено_строк_в_базе': len(к_удалению)}
    if not к_удалению:
        c.close()
        итог['режим'] = 'нечего удалять'
        print('===ИТОГ===')
        print(json.dumps(итог, ensure_ascii=False, indent=1))
        return 0

    бэкап = os.path.join(DIR, 'udalyonnye-ne-kapeks-%s.jsonl' % time.strftime('%d%m-%H%M'))
    with io.open(бэкап, 'w', encoding='utf-8') as f:
        for з in к_удалению:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    итог['бэкап'] = os.path.basename(бэкап)
    try:
        import shutil
        shutil.copyfile(бэкап, os.path.join(r'C:\seostat\drop\drop-storage',
                                            os.path.basename(бэкап)))
    except Exception:  # noqa: BLE001
        pass

    итог['примеры'] = [{'компания': з['компания'], 'тип': з['тип'],
                        'что': (з['что'] or '')[:90]} for з in к_удалению[:6]]

    if проба:
        c.close()
        итог['режим'] = 'проба, ничего не удалено'
        print('===ИТОГ===')
        print(json.dumps(итог, ensure_ascii=False, indent=1))
        return 0

    было = c.execute('select count(*) from signals').fetchone()[0]
    удалено = 0
    for inn, url, _ in пары:
        cur = c.execute('delete from signals where inn=? and source_url=?', (inn, url))
        удалено += cur.rowcount
    c.commit()
    стало = c.execute('select count(*) from signals').fetchone()[0]
    c.close()
    итог.update({'сигналов_было': было, 'сигналов_стало': стало, 'удалено': удалено})
    print('===ИТОГ===')
    print(json.dumps(итог, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
