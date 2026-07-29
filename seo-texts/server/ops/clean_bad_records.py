# -*- coding: utf-8 -*-
"""Убрать из базы записи, которые проверка признала недостоверными.

Три адреса, найденные адверсариальной проверкой 29.07. Все три опаснее
пропуска: пропуск виден продажнику, а неверная запись выглядит рабочей.

1. СФАБРИКОВАННЫЙ НОМЕР. У ИНН 3525392360 за Перхиным В. Б. записан
   «8 (8175) 54-15-00 доб. 0100». На странице vld35.ru/company/staff базовый
   номер принадлежит ПРИЁМНОЙ, а у Перхина совсем другой — разбор склеил базу
   одного человека с добавочным другого. Продажник набрал бы и попал не туда.

2. ДОЛЖНОСТЬ, ПЕРЕВЁРНУТАЯ ОБРЕЗКОЙ. «Заместитель главного инженера»
   сохранилось как «главного инженера», «Зам. ген. директора по техническим
   вопросам» — как «директора по техническим». Заместитель это НЕ главный:
   роль завышена, и в выгрузке человек стоит выше, чем должен. Не удаляем —
   возвращаем приставку в текст должности и пересчитываем роль.

3. ЧУЖОЙ ИНН ИЗ-ЗА ОБЩЕГО ДОМЕНА ХОЛДИНГА. Два файла кэша привязаны не к той
   компании: mechel.ru делят Мечел и Московский коксогазовый завод, sibur.ru —
   СИБУР и его дочерняя лаборатория. Контактов оттуда пока не записано, но
   привязка ошибочна и выстрелит при следующем прогоне — помечаем в stage_log,
   чтобы резолвер их больше не трогал.

По умолчанию СУХОЙ ПРОГОН. Удаляемое сперва пишется в журнал с fsync.
Запуск: python clean_bad_records.py [--apply]
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ПРИМЕНИТЬ = '--apply' in sys.argv
ЖУРНАЛ = r'C:\seostat\drop\bad_records_removed.jsonl'

db = EDB.EnrichDB()
e = db.cx

# приставки, которые обрезка съедала, переворачивая смысл должности
_ЗАМ = re.compile(r'^(?:главного|директора|начальника)\b', re.I)
_СПОРНЫЕ_ДОМЕНЫ = (('5003003915', '7703370008', 'mechel.ru'),
                   ('2462004363', '7731367261', 'sibur.ru'))


def main():
    out = {'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой прогон (--apply)'}
    убрать, поправить = [], []

    # 1. склеенный номер
    for r in e.execute(
            "SELECT rowid, inn, phone, person, role, source_url FROM phone_contacts "
            "WHERE inn='3525392360' AND phone LIKE '%8175%' AND phone LIKE '%0100%'"):
        убрать.append(dict(zip(('rowid', 'inn', 'phone', 'person', 'role',
                                'source_url'), r)))
    out['склеенных_номеров'] = len(убрать)

    # 2. должность, у которой обрезка съела «заместитель»
    for r in e.execute("SELECT rowid, inn, person, post, role FROM people "
                       "WHERE post<>''"):
        rowid, inn, person, post, role = r
        if _ЗАМ.match((post or '').strip()):
            нов = 'заместитель ' + post.strip()
            поправить.append({'rowid': rowid, 'инн': inn, 'фио': person,
                              'было': post, 'стало': нов,
                              'роль_была': role,
                              'роль_станет': EDB.EnrichDB._canon_role(нов)})
    out['должностей_перевёрнутых'] = len(поправить)
    out['примеры_должностей'] = поправить[:8]
    out['примеры_номеров'] = [{'тел': x['phone'], 'кто': x['person'],
                               'ссылка': (x['source_url'] or '')[:70]}
                              for x in убрать]

    if ПРИМЕНИТЬ:
        if убрать:
            with io.open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
                for x in убрать:
                    f.write(json.dumps({'причина': 'номер склеен из двух строк '
                                        'страницы: база приёмной + чужой '
                                        'добавочный', 'запись': x},
                                       ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
            e.executemany('DELETE FROM phone_contacts WHERE rowid=?',
                          [(x['rowid'],) for x in убрать])
        for x in поправить:
            e.execute('UPDATE people SET post=?, role=? WHERE rowid=?',
                      (x['стало'], x['роль_станет'], x['rowid']))
        # 3. спорные привязки по общему домену холдинга
        for свой, чужой, дом in _СПОРНЫЕ_ДОМЕНЫ:
            e.execute('INSERT OR REPLACE INTO stage_log(inn, stage, detail, ts) '
                      'VALUES(?,?,?,datetime("now"))',
                      (свой, 'domain_shared',
                       f'домен {дом} общий с ИНН {чужой}: привязывать по домену '
                       f'НЕЛЬЗЯ, только по ИНН'))
        e.commit()
        out['удалено'] = len(убрать)
        out['исправлено_должностей'] = len(поправить)
        out['помечено_спорных_доменов'] = len(_СПОРНЫЕ_ДОМЕНЫ)
        out['журнал'] = ЖУРНАЛ
    print(json.dumps(out, ensure_ascii=False, indent=1)[:4000])
    print(json.dumps({k: v for k, v in out.items()
                      if not isinstance(v, list)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
