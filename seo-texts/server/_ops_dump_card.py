# -*- coding: utf-8 -*-
"""Карточка компании ЦЕЛИКОМ в файл на дропе (stdout раннера обрезается хвостом).

Запуск: python _ops_dump_card.py ИНН [имя_файла]
"""
import io
import json
import os
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ИНН = next((a for a in sys.argv[1:] if a.isdigit()), '')
ИМЯ = next((a for a in sys.argv[1:] if a.endswith('.json')), f'card_{ИНН}.json')
# Дроп РАЗДАЁТ не C:\seostat\drop, а вложенную drop-storage: файл, положенный
# уровнем выше, скачивается как 404. Проверено на agg1.jsonl и на этой карточке.
ПУТЬ = r'C:\seostat\drop\drop-storage' + '\\' + ИМЯ
e = EDB.EnrichDB().cx


def строки(sql, args=()):
    cur = e.execute(sql, args)
    поля = [d[0] for d in cur.description]
    return [dict(zip(поля, r)) for r in cur.fetchall()]


def main():
    c = строки('select * from companies where inn=?', (ИНН,))
    out = {'компания': c[0] if c else {},
           'люди': строки('select person, post, role, phone, email, source, '
                          'source_url, observed_at from people where inn=?', (ИНН,)),
           'телефоны': строки('select phone, person, role, source, source_url '
                              'from phone_contacts where inn=?', (ИНН,)),
           'почты': строки('select email, person, role, mx_ok, source, source_url '
                           'from emails where inn=?', (ИНН,)),
           'сигналы': строки('select event_type, what, sum, hotness, source_url, ts '
                             'from signals where inn=?', (ИНН,)),
           'этапы': строки('select stage, detail, ts from stage_log where inn=?',
                           (ИНН,))}
    os.makedirs(os.path.dirname(ПУТЬ), exist_ok=True)
    with io.open(ПУТЬ, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    print(json.dumps({'файл': ПУТЬ, 'людей': len(out['люди']),
                      'телефонов': len(out['телефоны']),
                      'почт': len(out['почты'])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
