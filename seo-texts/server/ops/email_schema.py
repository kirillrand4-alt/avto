# -*- coding: utf-8 -*-
"""Схема корпоративной почты -> адрес человека, у которого адреса нет (способ А8).

Смысл. После прогонов в таблице people лежат люди С ИМЕНЕМ И ДОЛЖНОСТЬЮ, но
БЕЗ почты: «Федоськин Михаил Петрович, главный энергетик» с грифа «УТВЕРЖДАЮ»
или со страницы руководства. Звонить есть куда, писать — некуда. При этом у той
же компании часто известны ДРУГИЕ адреса на своём домене, и по ним видно
правило: `i.familiya@`, `familiya@`, `if@`. Правило плюс ФИО дают адрес.

Три рубежа честности, иначе это генератор выдумок:
  1. схема выводится ТОЛЬКО из адресов, у которых известно ФИО владельца, и
     ТОЛЬКО если она подтверждается минимум ДВУМЯ адресами компании. Одно
     совпадение — это совпадение, а не правило;
  2. кандидат проверяется SMTP-пробой RCPT TO без отправки письма; пишется
     лишь ответ smtp_ok. Домен-catch-all (принимает любой адрес) отбрасывается
     целиком — там проверить нельзя, а значит и записывать нельзя;
  3. в базу адрес идёт с source='схема+smtp' и пометкой правила в source_url,
     чтобы происхождение было видно и его можно было отозвать.

Ни одного письма при этом не отправляется: RCPT TO завершается QUIT. Это не
рассылка и холда не касается.

По умолчанию СУХОЙ ПРОГОН. Запуск:
    python email_schema.py [бюджет_сек] [--apply] [--only sales] [--limit N]
"""
import io
import json
import os
import re
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB          # noqa: E402
import enrich_contacts as EC     # noqa: E402

_поз = [a for a in sys.argv[1:] if not a.startswith('--')]
БЮДЖЕТ = float(_поз[0]) if _поз else 900.0
ПРИМЕНИТЬ = '--apply' in sys.argv
ЛИМИТ = int(sys.argv[sys.argv.index('--limit') + 1]
            if '--limit' in sys.argv else 100000)
ПОТОК = r'C:\seostat\drop\email_schema.jsonl'
НАЧАЛО = time.time()

db = EDB.EnrichDB()
e = db.cx

# Транслитерация как её пишут в корпоративной почте (не ГОСТ, а обиход):
# «щ» -> sch, «ю» -> yu, мягкий и твёрдый знаки выпадают.
_ЛАТ = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya', '-': '-',
}
# частые расхождения: «х» пишут и как h, «ц» как c, «й» как i — держим варианты
_ВАРИАНТЫ = {'kh': ('h',), 'ts': ('c',), 'y': ('i',), 'ya': ('ia',),
             'yu': ('iu',), 'zh': ('j',), 'sch': ('shch', 'sh'),
             'ks': ('x',)}


def лат(с):
    out = []
    for ч in (с or '').lower():
        out.append(_ЛАТ.get(ч, ч if ч.isalnum() else ''))
    return ''.join(out)


def варианты(с):
    """Написания одного слова: kh/h, ts/c и т. п. Комбинаторику держим малой."""
    из = {лат(с)}
    for a, бы in _ВАРИАНТЫ.items():
        для = set()
        for x in из:
            for b in бы:
                if a in x:
                    для.add(x.replace(a, b))
        из |= для
        if len(из) > 24:
            break
    return из


def части(фио):
    ч = [x for x in re.split(r'[\s.]+', (фио or '').strip()) if x]
    if len(ч) < 2:
        return None
    # Порядок бывает и «Фамилия Имя Отчество», и «Имя Отчество Фамилия».
    # Различает их ОТЧЕСТВО: если оно посередине — значит первым идёт имя.
    # (Проверка на ч[2] здесь была бы ровно наоборот и переворачивала
    #  нормальное «Федоськин Михаил Петрович» в «Михаил Петрович Федоськин»,
    #  после чего фамилией считалось имя. Поймано тестом.)
    if len(ч) == 3 and re.search(r'(ович|евич|овна|евна|ична|инична)$',
                                 ч[1], re.I):
        ч = [ч[2], ч[0], ч[1]]      # Имя Отчество Фамилия -> Фамилия Имя Отчество
    return {'ф': ч[0], 'и': ч[1] if len(ч) > 1 else '',
            'о': ч[2] if len(ч) > 2 else ''}


def кандидаты(фио):
    """{локальная_часть: имя_схемы} по всем ходовым правилам."""
    p = части(фио)
    if not p:
        return {}
    из = {}
    for ф in варианты(p['ф']):
        и_в = варианты(p['и']) if p['и'] else {''}
        о_в = варианты(p['о']) if p['о'] else {''}
        for и in и_в:
            for о in о_в:
                и1, о1 = (и[:1], о[:1])
                правила = {
                    f'{и1}.{ф}': 'и.фамилия', f'{и1}{ф}': 'ифамилия',
                    f'{ф}.{и1}': 'фамилия.и', f'{ф}_{и1}': 'фамилия_и',
                    f'{ф}{и1}': 'фамилияи', ф: 'фамилия',
                    f'{и}.{ф}': 'имя.фамилия', f'{и}_{ф}': 'имя_фамилия',
                    f'{и}{ф}': 'имяфамилия', f'{ф}.{и}': 'фамилия.имя',
                }
                if о1:
                    правила[f'{и1}{о1}{ф}'] = 'иофамилия'
                    правила[f'{ф}{и1}{о1}'] = 'фамилияио'
                    правила[f'{и1}.{о1}.{ф}'] = 'и.о.фамилия'
                for лок, имя in правила.items():
                    if лок and лок not in из:
                        из[лок] = имя
    return из


_ПУБЛИЧНЫЕ = {'mail.ru', 'yandex.ru', 'ya.ru', 'gmail.com', 'bk.ru', 'inbox.ru',
              'list.ru', 'rambler.ru', 'internet.ru', 'yahoo.com', 'icloud.com'}


def свой_домен(inn):
    r = e.execute('SELECT site FROM companies WHERE inn=?', (inn,)).fetchone()
    d = EC._domain((r or [''])[0] or '')
    return d.lower() if d else ''


def вывести_схему(inn, дом):
    """Правило почты компании: подтверждается минимум ДВУМЯ адресами с ФИО."""
    голоса = {}
    строки = list(e.execute(
        'SELECT email, person FROM emails WHERE inn=? AND person<>""', (inn,)))
    строки += [(r[0], r[1]) for r in e.execute(
        'SELECT email, person FROM people WHERE inn=? AND email<>"" '
        'AND person<>""', (inn,))]
    примеры = {}
    for адрес, фио in строки:
        адрес = (адрес or '').lower().strip()
        if '@' not in адрес or not адрес.endswith('@' + дом):
            continue
        лок = адрес.split('@')[0]
        схемы = кандидаты(фио)
        имя = схемы.get(лок)
        if имя:
            голоса[имя] = голоса.get(имя, 0) + 1
            примеры.setdefault(имя, []).append(адрес)
    if not голоса:
        return '', 0, []
    имя, n = max(голоса.items(), key=lambda x: x[1])
    return (имя, n, примеры.get(имя, [])) if n >= 2 else ('', n, [])


def по_схеме(фио, имя_схемы):
    for лок, имя in кандидаты(фио).items():
        if имя == имя_схемы:
            return лок
    return ''


def main():
    цели = [r[0] for r in e.execute(
        'SELECT DISTINCT inn FROM people WHERE person<>"" '
        'AND (email IS NULL OR email="")')][:ЛИМИТ]
    out = {'компаний_с_безадресными': len(цели), 'схема_выведена': 0,
           'кандидатов': 0, 'catch_all_доменов': 0, 'подтверждено_smtp': 0,
           'отвергнуто_smtp': 0, 'не_проверено': 0, 'записано': 0,
           'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой прогон (--apply)',
           'схемы': {}, 'примеры': []}
    ф = io.open(ПОТОК, 'a', encoding='utf-8')
    for inn in цели:
        if time.time() - НАЧАЛО > БЮДЖЕТ:
            break
        дом = свой_домен(inn)
        # публичная почта схемы не имеет: на mail.ru адрес выбирает сам
        # человек, и вывести правило по двум коллегам нельзя
        if not дом or дом in _ПУБЛИЧНЫЕ:
            continue
        имя_схемы, голосов, примеры = вывести_схему(inn, дом)
        if not имя_схемы:
            continue
        out['схема_выведена'] += 1
        out['схемы'][имя_схемы] = out['схемы'].get(имя_схемы, 0) + 1
        # домен-catch-all проверяем ОДИН раз на компанию
        проба = EC.smtp_verify(f'zz-nikogo-net-{inn}@{дом}')
        if проба == 'catch-all':
            out['catch_all_доменов'] += 1
            ф.write(json.dumps({'inn': inn, 'дом': дом, 'схема': имя_схемы,
                                'итог': 'catch-all'}, ensure_ascii=False) + '\n')
            continue
        люди = list(e.execute(
            'SELECT person, post, role FROM people WHERE inn=? AND person<>"" '
            'AND (email IS NULL OR email="")', (inn,)))
        for фио, пост, роль in люди:
            if time.time() - НАЧАЛО > БЮДЖЕТ:
                break
            лок = по_схеме(фио, имя_схемы)
            if not лок:
                continue
            адрес = f'{лок}@{дом}'
            out['кандидатов'] += 1
            итог = EC.smtp_verify(адрес)
            if итог == 'smtp_ok':
                out['подтверждено_smtp'] += 1
                if len(out['примеры']) < 14:
                    out['примеры'].append(
                        {'инн': inn, 'фио': фио, 'должность': пост,
                         'адрес': адрес, 'схема': имя_схемы,
                         'подтвердили_адреса': примеры[:2]})
                if ПРИМЕНИТЬ:
                    db.add_email(inn, адрес, role=роль or '', person=фио,
                                 mx_ok=1, source='схема+smtp',
                                 source_url=f'схема {имя_схемы} по {примеры[:2]}')
                    e.execute('UPDATE people SET email=? WHERE inn=? AND '
                              'person=? AND (email IS NULL OR email="")',
                              (адрес, inn, фио))
                    out['записано'] += 1
            elif итог == 'smtp_reject':
                out['отвергнуто_smtp'] += 1
            else:
                out['не_проверено'] += 1
            ф.write(json.dumps({'inn': inn, 'фио': фио, 'адрес': адрес,
                                'схема': имя_схемы, 'итог': итог},
                               ensure_ascii=False) + '\n')
            time.sleep(1.2)      # вежливость к чужому SMTP
        if ПРИМЕНИТЬ:
            e.commit()
        ф.flush()
        os.fsync(ф.fileno())
    ф.close()
    print(json.dumps(out, ensure_ascii=False, indent=1)[:5000])
    print(json.dumps({k: v for k, v in out.items() if k != 'примеры'},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
