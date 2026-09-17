# -*- coding: utf-8 -*-
r"""Выгрузка ВСЕХ сигналов в CSV: событие, компания, сумма, стадия, ссылка.

Стадию считаем на лету по типу и тексту (поля stage в базе ещё нет — это задача 5
ТЗ, миграция не запускалась). Правила те же, что в stadii.py.
"""
import csv
import io
import json
import os
import re
import sqlite3

БАЗА = r'C:\sender\enrich.db'
DIR = r'C:\sender\server'

ПРОЕКТ = ('планиру', 'намерен', 'построит', 'создаст', 'инвестиц', 'соглашен',
          'резидент', 'проект', 'анонс', 'разработ', 'вложит', 'заявил')
СТРОЙКА = ('строит', 'строительств', 'возвод', 'монтаж', 'ведутся работ', 'котлован')
ПУСК = ('запуск', 'запустил', 'открыл', 'ввёл', 'ввод в эксплуатац', 'пусконаладк',
        'первая очередь готов', 'завершил строительств')
РАСШИР = ('расширен', 'модерниз', 'техперевооруж', 'реконструкц', 'обновил',
          'увеличил мощност', 'вторая очередь')


def стадия(тип, текст):
    t = ((тип or '') + ' ' + (текст or '')).lower()
    if any(k in t for k in ПУСК):
        return '3 пуск'
    if any(k in t for k in СТРОЙКА):
        return '2 стройка'
    if any(k in t for k in РАСШИР):
        return '4 расширение'
    if any(k in t for k in ПРОЕКТ):
        return '1 проект'
    return '0 не определена'


def main():
    c = sqlite3.connect('file:%s?mode=ro' % БАЗА, uri=True, timeout=60)
    строки = c.execute(
        "select s.inn, coalesce(cmp.name,''), coalesce(cmp.division,''), "
        "coalesce(cmp.region,''), s.source, s.event_type, s.what, coalesce(s.sum,''), "
        "s.hotness, coalesce(s.inn_conf,''), s.source_url, substr(s.updated_at,1,16), "
        "coalesce(s.ts,''), coalesce(cmp.site,''), coalesce(cmp.best_email,'') "
        'from signals s left join companies cmp on cmp.inn = s.inn '
        'order by s.rowid desc').fetchall()
    c.close()

    имя = 'signaly-vse-%s.csv' % __import__('time').strftime('%d%m')
    путь = os.path.join(DIR, имя)
    with io.open(путь, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['ИНН', 'компания', 'направление', 'регион', 'источник',
                    'тип события', 'что происходит', 'сумма', 'важность', 'стадия',
                    'уверенность в ИНН', 'ссылка', 'узнали', 'дата события',
                    'сайт', 'почта'])
        for р in строки:
            (inn, name, div, reg, src, et, what, sm, hot, conf, url, upd, ts, site, mail) = р
            w.writerow([inn, name, div, reg, src, et,
                        re.sub(r'\s+', ' ', what or '')[:600], sm, hot,
                        стадия(et, what), conf, url, upd, ts, site, mail])
        f.flush()
        os.fsync(f.fileno())
    try:
        import shutil
        shutil.copyfile(путь, os.path.join(r'C:\seostat\drop\drop-storage', имя))
    except Exception:  # noqa: BLE001
        pass
    print('===ИТОГ===')
    print(json.dumps({'строк': len(строки), 'файл': имя,
                      'байт': os.path.getsize(путь)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
