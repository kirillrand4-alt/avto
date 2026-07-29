# -*- coding: utf-8 -*-
"""Расшифровка инициалов сшивкой источников (способ А6).

Наблюдение из engineers-lens: документы закупок дают «Оськин К.В.», а страница
руководства — «Оськин Константин Владимирович». Это ОДИН человек, и без сшивки
он лежит в базе двумя записями: у одной есть должность и дата из документа, у
другой — полное имя и телефон с сайта.

Правило сшивки намеренно строгое: совпадает фамилия И обе буквы инициалов с
началом имени и отчества, и обе записи относятся к ОДНОЙ компании. Иначе
однофамильцы внутри крупного завода слепятся в одного человека — ровно та
ловушка В3, о которой предупреждает разбор.

Победитель — запись с ПОЛНЫМ именем; из короткой к ней переносятся непустые
должность, телефон, почта и ссылка на источник, если у полной их нет. Короткая
после переноса удаляется, но сперва пишется в people_merged.jsonl.

По умолчанию СУХОЙ ПРОГОН. Применить: --apply
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ПРИМЕНИТЬ = '--apply' in sys.argv
ЖУРНАЛ = r'C:\seostat\drop\people_merged.jsonl'

_КРАТКО = re.compile(r'^([А-ЯЁ][а-яё\-]{2,})\s+([А-ЯЁ])\.\s?([А-ЯЁ])\.?$')
_ПОЛНО = re.compile(r'^([А-ЯЁ][а-яё\-]{2,})\s+([А-ЯЁ][а-яё]{1,})\s+([А-ЯЁ][а-яё]{1,})$')


def main():
    db = EDB.EnrichDB()
    e = db.cx
    строки = [dict(zip(('rowid', 'inn', 'person', 'post', 'role', 'phone',
                        'email', 'source', 'source_url', 'observed_at'), r))
              for r in e.execute(
        'select rowid, inn, person, post, role, phone, email, source, '
        'source_url, observed_at from people')]

    по_инн = {}
    for s in строки:
        по_инн.setdefault(s['inn'], []).append(s)

    пары = []
    for inn, люди in по_инн.items():
        кратк = [(m, x) for x in люди
                 for m in [_КРАТКО.match((x['person'] or '').strip())] if m]
        полн = [(m, x) for x in люди
                for m in [_ПОЛНО.match((x['person'] or '').strip())] if m]
        for mk, к in кратк:
            фам, и1, и2 = mk.group(1).lower(), mk.group(2), mk.group(3)
            for mp, п in полн:
                if mp.group(1).lower() != фам:
                    continue
                if mp.group(2)[0] != и1 or mp.group(3)[0] != и2:
                    continue
                пары.append((к, п))
                break

    out = {'людей_всего': len(строки), 'пар_найдено': len(пары),
           'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой прогон (применить: --apply)',
           'примеры': [{'было': к['person'], 'стало': п['person'],
                        'должность_из_короткой': к['post'],
                        'инн': к['inn']} for к, п in пары[:12]]}

    if ПРИМЕНИТЬ and пары:
        os.makedirs(os.path.dirname(ЖУРНАЛ), exist_ok=True)
        with io.open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
            for к, п in пары:
                f.write(json.dumps({'удалена': к, 'слита_в': п['person'],
                                    'инн': к['inn']}, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
        for к, п in пары:
            # непустое из короткой переносим только туда, где у полной пусто
            поля = {}
            for поле in ('post', 'phone', 'email', 'source_url'):
                if not (п.get(поле) or '').strip() and (к.get(поле) or '').strip():
                    поля[поле] = к[поле]
            if поля:
                # роль пересчитываем по перенесённой должности
                if 'post' in поля:
                    поля['role'] = EDB.EnrichDB._canon_role(поля['post'])
                sets = ', '.join(f'{k}=?' for k in поля)
                e.execute(f'update people set {sets} where rowid=?',
                          list(поля.values()) + [п['rowid']])
            e.execute('delete from people where rowid=?', (к['rowid'],))
        e.commit()
        out['слито'] = len(пары)
        out['журнал'] = ЖУРНАЛ
        out['осталось'] = e.execute('select count(*) from people').fetchone()[0]
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
