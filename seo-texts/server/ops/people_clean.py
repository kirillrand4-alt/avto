# -*- coding: utf-8 -*-
"""Вычистить из people записи, которые уже не проходят проверку на ФИО.

Правила разбора ужесточались по ходу прогонов (мусор ловился глазами на
карточках: «Формула Дома», «Технополис Москва», «Москве Тимошенко Анатолий»),
а строки, записанные ДО ужесточения, остались в базе и продолжают показываться
в панели. Прогоняем каждую через актуальную проверку и удаляем непрошедшие.

По умолчанию СУХОЙ ПРОГОН: печатает, что удалил бы. Удаляет только с --apply —
и перед удалением складывает удаляемое в people_removed.jsonl, чтобы решение
можно было пересмотреть, не повторяя обход.
"""
import io
import json
import os
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB       # noqa: E402
import enrich_contacts as EC  # noqa: E402

ПРИМЕНИТЬ = '--apply' in sys.argv
ЖУРНАЛ = r'C:\seostat\drop\people_removed.jsonl'


def main():
    db = EDB.EnrichDB()
    e = db.cx
    строки = list(e.execute(
        'select rowid, inn, person, post, role, phone, email, source_url from people'))
    плохие = []
    for rid, inn, фио, post, role, ph, em, url in строки:
        # актуальная проверка: то же, чем сейчас пользуется разбор страниц
        if EC._фио(фио or '') != (фио or '').strip():
            плохие.append({'rowid': rid, 'inn': inn, 'person': фио, 'post': post,
                           'role': role, 'phone': ph, 'email': em,
                           'source_url': url})
    out = {'всего': len(строки), 'не_проходят_проверку': len(плохие),
           'режим': 'УДАЛЕНИЕ' if ПРИМЕНИТЬ else 'сухой прогон',
           'примеры': [{'фио': x['person'], 'должность': x['post']}
                       for x in плохие[:15]]}
    if ПРИМЕНИТЬ and плохие:
        os.makedirs(os.path.dirname(ЖУРНАЛ), exist_ok=True)
        with io.open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
            for x in плохие:
                f.write(json.dumps(x, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
        e.executemany('delete from people where rowid=?',
                      [(x['rowid'],) for x in плохие])
        e.commit()
        out['удалено'] = len(плохие)
        out['журнал'] = ЖУРНАЛ
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
