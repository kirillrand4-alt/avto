# -*- coding: utf-8 -*-
"""Откат контактов, записанных кэш-прогонами не тому ИНН.

Оба прогона по кэшу доставали ИНН владельца поиском `site LIKE '%домен%'`.
Подстрока склеила разные компании: «ozm.ru» вошла в «ao-ozm.ru» (телефоны
опытного завода «Микрон» записались заводу «Механик»), «zti.ru» — в «o-zti.ru».
Отдельно есть случаи, где на ОДНОМ домене честно сидят два юрлица
(halopolymer.ru, europlast.ru) — там привязка не восстанавливается в принципе,
и такие записи тоже уходят: чужой контакт хуже отсутствующего.

Что удаляем — ровно то, что эти прогоны и писали: строки с источниками
«сайт компании» и «кэш:перечитан» у пострадавших ИНН, добавленные в день
прогона. Всё удаляемое сперва пишется в cache_misattrib_removed.jsonl.

По умолчанию СУХОЙ ПРОГОН. Запуск: python undo_cache_misattrib.py [--apply]
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ПРИМЕНИТЬ = '--apply' in sys.argv
ПОТОК = r'C:\seostat\drop\pagecache_roles.jsonl'
ЖУРНАЛ = r'C:\seostat\drop\cache_misattrib_removed.jsonl'
ИСТОЧНИКИ = ('сайт компании', 'кэш:перечитан')
ДЕНЬ = '2026-07-29'

db = EDB.EnrichDB()
e = db.cx


def расхождения():
    """Пары «ИНН из имени файла -> ИНН, под который записали» из потока."""
    из = []
    if not os.path.exists(ПОТОК):
        return из
    for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
        try:
            x = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        m = re.match(r'(\d{10}|\d{12})', str(x.get('файл') or ''))
        if not m or not x.get('inn'):
            continue
        if m.group(1) != str(x['inn']):
            из.append({'файл': x['файл'], 'правильный': m.group(1),
                       'ошибочный': str(x['inn'])})
    # один и тот же файл встречается в потоке дважды (повторный круг)
    свод = {}
    for x in из:
        свод[(x['правильный'], x['ошибочный'])] = x
    return list(свод.values())


def main():
    пары = расхождения()
    чужие = sorted({x['ошибочный'] for x in пары})
    out = {'пар_расхождения': len(пары), 'пострадавших_инн': len(чужие),
           'пары': пары[:14],
           'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой прогон (--apply)'}
    if not чужие:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return
    места = ','.join('?' * len(чужие))
    ист = ','.join('?' * len(ИСТОЧНИКИ))
    тел = [dict(zip(('rowid', 'inn', 'phone', 'person', 'role', 'source',
                     'source_url', 'updated_at'), r))
           for r in e.execute(
        f'SELECT rowid, inn, phone, person, role, source, source_url, updated_at '
        f'FROM phone_contacts WHERE inn IN ({места}) AND source IN ({ист}) '
        f'AND updated_at LIKE ?', чужие + list(ИСТОЧНИКИ) + [ДЕНЬ + '%'])]
    поч = [dict(zip(('rowid', 'inn', 'email', 'person', 'role', 'source',
                     'source_url', 'updated_at'), r))
           for r in e.execute(
        f'SELECT rowid, inn, email, person, role, source, source_url, updated_at '
        f'FROM emails WHERE inn IN ({места}) AND source IN ({ист}) '
        f'AND updated_at LIKE ?', чужие + list(ИСТОЧНИКИ) + [ДЕНЬ + '%'])]
    люд = [dict(zip(('rowid', 'inn', 'person', 'post', 'source', 'source_url',
                     'updated_at'), r))
           for r in e.execute(
        f'SELECT rowid, inn, person, post, source, source_url, updated_at '
        f'FROM people WHERE inn IN ({места}) AND source IN ({ист}) '
        f'AND updated_at LIKE ?', чужие + list(ИСТОЧНИКИ) + [ДЕНЬ + '%'])]
    out.update({'телефонов_к_удалению': len(тел), 'почт_к_удалению': len(поч),
                'людей_к_удалению': len(люд),
                'примеры_телефонов': [{'инн': x['inn'], 'тел': x['phone'],
                                       'ссылка': (x['source_url'] or '')[:60]}
                                      for x in тел[:10]]})
    if ПРИМЕНИТЬ and (тел or поч or люд):
        with io.open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
            for вид, набор in (('phone_contacts', тел), ('emails', поч),
                               ('people', люд)):
                for x in набор:
                    f.write(json.dumps({'таблица': вид, 'причина':
                                        'кэш записан чужому ИНН (поиск по домену '
                                        'подстрокой)', 'запись': x},
                                       ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
        for табл, набор in (('phone_contacts', тел), ('emails', поч),
                            ('people', люд)):
            e.executemany(f'DELETE FROM {табл} WHERE rowid=?',
                          [(x['rowid'],) for x in набор])
        e.commit()
        out['удалено'] = {'телефонов': len(тел), 'почт': len(поч),
                          'людей': len(люд)}
        out['журнал'] = ЖУРНАЛ
    print(json.dumps(out, ensure_ascii=False, indent=1)[:5000])
    print(json.dumps({k: v for k, v in out.items()
                      if not isinstance(v, list)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
