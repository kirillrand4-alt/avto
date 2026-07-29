# -*- coding: utf-8 -*-
"""Вычистить брак прежнего источника zakupki:eis. По умолчанию СУХОЙ ПРОГОН.

Два РАЗНЫХ случая, и лечатся они по-разному — валить их в одну кучу нельзя.

1. ТЕЛЕФОН ПЛОЩАДКИ, А НЕ КОМПАНИИ. Один номер стоит у трёх и более разных
   ИНН — это подвал самого ЕИС: 8-499-949-47-40 и 8-800-333-80-00 это его
   служба поддержки, она у нас записана восьми и четырём компаниям
   соответственно. Такую строку УДАЛЯЕМ: продажник набрал бы техподдержку
   госпортала. Порог именно 3, а не 2: два юрлица одного холдинга законно
   делят приёмную, и на двойках чистка начала бы бить по живому.

2. ИМЯ ИЗ ВЁРСТКИ СТРАНИЦЫ («Опросы Статистика Карта»). Здесь удалять контакт
   целиком неправильно: сломано ИЗВЛЕЧЕНИЕ ИМЕНИ, а сам адрес или номер мог
   приехать с карточки и быть годным. Поэтому имя СТИРАЕМ, контакт оставляем —
   кроме случая, когда номер заодно попал в список площадочных: тогда мусор и
   там, и там, и строка уходит целиком.

Удаляемое сперва в журнал с fsync — как и при откате чужих привязок, чтобы
решение было обратимым.
"""
import io
import json
import os
import re
import sys
sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB

ПРИМЕНИТЬ = '--apply' in sys.argv
ЖУРНАЛ = r'C:\seostat\drop\eis_dirt_removed.jsonl'
ПОРОГ = 3

_ВЁРСТКА = re.compile(
    r'опрос|статистик|карта|главн|новост|контакт|поиск|меню|версия|'
    r'реестр|закупк|разде|войти|регистрац|подписк|документ|уведомл|'
    r'сведени|информац|обратн|связь|печат|скачат|подробн', re.I)

db = EDB.EnrichDB()
e = db.cx
print(json.dumps({'старт': True, 'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ
                  else 'сухой прогон (--apply)'}, ensure_ascii=False))

площадочные = {r[0] for r in e.execute(
    "SELECT phone FROM phone_contacts WHERE lower(source) LIKE '%zakupki%' "
    'GROUP BY 1 HAVING count(distinct inn)>=?', (ПОРОГ,))}
удалить_тел = [dict(zip(('rowid', 'inn', 'phone', 'person', 'role', 'source_url'), r))
               for r in e.execute(
    'SELECT rowid, inn, phone, person, role, source_url FROM phone_contacts '
    "WHERE lower(source) LIKE '%zakupki%' AND phone IN ("
    + ','.join('?' * len(площадочные)) + ')', tuple(площадочные))] \
    if площадочные else []

стереть_имя = {'phone_contacts': [], 'emails': []}
удалить_ещё = []
for табл in ('phone_contacts', 'emails'):
    ключ = 'phone' if табл == 'phone_contacts' else 'email'
    for rowid, inn, кто, что, url in e.execute(
            f'SELECT rowid, inn, person, {ключ}, source_url FROM {табл} '
            "WHERE lower(source) LIKE '%zakupki%' AND person<>''"):
        if not _ВЁРСТКА.search(кто or ''):
            continue
        зап = {'rowid': rowid, 'инн': inn, 'имя': кто, 'контакт': что,
               'ссылка': (url or '')[:80], 'таблица': табл}
        if табл == 'phone_contacts' and что in площадочные:
            удалить_ещё.append(зап)   # уже уйдёт вместе с площадочными
        else:
            стереть_имя[табл].append(зап)

итог = {'площадочных_номеров': len(площадочные),
        'строк_под_ними_к_удалению': len(удалить_тел),
        'имён_из_вёрстки_к_стиранию': {k: len(v) for k, v in стереть_имя.items()},
        'из_них_уйдут_вместе_с_номером': len(удалить_ещё)}

if ПРИМЕНИТЬ:
    with io.open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
        for x in удалить_тел:
            f.write(json.dumps({'причина': 'номер площадки ЕИС: стоит у '
                                f'{ПОРОГ}+ разных ИНН', 'запись': x},
                               ensure_ascii=False) + '\n')
        for табл, сп in стереть_имя.items():
            for x in сп:
                f.write(json.dumps({'причина': 'имя взято из вёрстки страницы, '
                                    'контакт оставлен', 'запись': x},
                                   ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    if удалить_тел:
        e.executemany('DELETE FROM phone_contacts WHERE rowid=?',
                      [(x['rowid'],) for x in удалить_тел])
    for табл, сп in стереть_имя.items():
        if сп:
            e.executemany(f'UPDATE {табл} SET person=? WHERE rowid=?',
                          [('', x['rowid']) for x in сп])
    e.commit()
    итог['журнал'] = ЖУРНАЛ

итог['телефонов_в_базе'] = e.execute(
    'SELECT count(*) FROM phone_contacts').fetchone()[0]
print(json.dumps({'примеры_площадочных': sorted(площадочные)[:8],
                  'примеры_удаляемых': удалить_тел[:5]},
                 ensure_ascii=False)[:1500])
print(json.dumps(итог, ensure_ascii=False))
