# -*- coding: utf-8 -*-
"""Выгрузить все должности и роли на дроп — дальше разбор идёт провайдером ВНЕ сервера.

Раннер один и выполняет задания по одному, а провайдерский разбор к серверу не
привязан: текст должности уже в базе, фетчить нечего. Поэтому выгружаем один
раз и всю тяжёлую работу делаем снаружи, не занимая очередь.
"""
import io
import json
import os
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ПУТЬ = r'C:\seostat\drop\drop-storage\roles_dump.json'
e = EDB.EnrichDB().cx


def main():
    люди = [dict(zip(('inn', 'person', 'post', 'role', 'source', 'source_url'), r))
            for r in e.execute(
        "SELECT inn, person, post, role, source, source_url FROM people "
        "WHERE ifnull(post,'')<>''")]
    тел = [dict(zip(('rowid', 'inn', 'phone', 'person', 'role', 'source'), r))
           for r in e.execute(
        "SELECT rowid, inn, phone, person, role, source FROM phone_contacts "
        "WHERE ifnull(role,'')<>'' AND role NOT IN "
        "('общий','приёмная','справочник','контакты компании (чеко)',"
        "'общий (со страницы)','общий (чеко)','с сайта (обход)')")]
    with io.open(ПУТЬ, 'w', encoding='utf-8') as f:
        json.dump({'люди': люди, 'телефоны': тел}, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    print(json.dumps({'файл': ПУТЬ, 'людей': len(люди),
                      'телефонов_с_ролью': len(тел)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
