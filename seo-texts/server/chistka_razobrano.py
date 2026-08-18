# -*- coding: utf-8 -*-
r"""Удалить отработанные файлы Зенки (zenno\razobrano) — 51 ГБ спущенного сырья.

Что это такое. Мост zenno_most.py разбирает выдачу Зенки: страницы уезжают в
pagecache (сжатыми, 16 раз легче), контакты — в enrich.db, а сами файлы
ПЕРЕНОСЯТСЯ в razobrano и больше не открываются никогда. Проверено по коду:
единственное упоминание razobrano вне переноса — счётчик файлов и максимальная
дата изменения; содержимое не читает никто.

Почему нельзя чистить подчистую. Мост определяет «Зенка встала» по свежести
файлов в gotovo и razobrano (dorabotka: tishina_min). Снеся всё, мы обнулим
этот сигнал, и сторож решит, что шаблон молчит. Поэтому свежие СУТКИ оставляем.

    python chistka_razobrano.py [дней]            посчитать (ничего не трогая)
    python chistka_razobrano.py [дней] --udalit   удалить старше N дней (по умолч. 1)
"""
import json
import os
import sys
import time

ZENNO = os.environ.get('ZENNO_DIR', r'C:\seostat\drop\zenno')
RAZOBRANO = os.path.join(ZENNO, 'razobrano')
ЖУРНАЛ = r'C:\sender\server\chistka-razobrano.jsonl'


def разобрать(дней=1, удалять=False):
    порог = time.time() - дней * 86400
    итог = {'папка': RAZOBRANO, 'держим_дней': дней, 'файлов_всего': 0,
            'под_удаление': 0, 'оставляем_свежих': 0, 'освободим_ГБ': 0.0,
            'удалено': 0, 'ошибок': 0}
    байт = 0
    свежесть = 0.0
    try:
        это = list(os.scandir(RAZOBRANO))
    except OSError as e:
        итог['беда'] = str(e)
        return итог
    for e in это:
        try:
            if not e.is_file():
                continue
            st = e.stat()
        except OSError:
            continue
        итог['файлов_всего'] += 1
        if st.st_mtime >= порог:
            итог['оставляем_свежих'] += 1
            свежесть = max(свежесть, st.st_mtime)
            continue
        итог['под_удаление'] += 1
        байт += st.st_size
        if удалять:
            try:
                os.remove(e.path)
                итог['удалено'] += 1
            except OSError:
                итог['ошибок'] += 1
    итог['освободим_ГБ'] = round(байт / 2**30, 2)
    итог['самый_свежий_остался'] = (
        time.strftime('%Y-%m-%d %H:%M', time.localtime(свежесть)) if свежесть
        else 'НЕТ — сигнал «Зенка молчит» обнулится, так делать нельзя')
    if удалять:
        with open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
            f.write(json.dumps({**итог, 'ts': time.strftime('%Y-%m-%dT%H:%M:%S')},
                               ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
    return итог


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    дней = next((int(a) for a in sys.argv[1:] if a.isdigit()), 1)
    print(json.dumps(разобрать(дней, '--udalit' in sys.argv),
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
