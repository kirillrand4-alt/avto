# -*- coding: utf-8 -*-
"""Куда делись техЛПР обхода: он насчитал 27, база приросла на 7.

Разница может быть трёх видов, и они требуют разного:
  1) человек уже был известен (дубль) — тогда всё честно, прироста и нет;
  2) его предприятие не попало в общую базу — надо чинить сборку;
  3) канон базы понизил роль, а счётчик обхода посчитал техническим — тогда
     врёт один из двух, и надо смотреть должность глазами.
Гадать нельзя: сегодня уже дважды «расхождение» оказывалось моей ошибкой.
"""
import csv
import io
import json
import os
import sys
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

НАХОДКИ = r'C:\seostat\drop\dept_dir_found.jsonl'
ДРОП = r'C:\seostat\drop\drop-storage'
ТЕХ = set(EDB.EnrichDB.TECH_ROLES)


def main():
    csv.field_size_limit(10 ** 7)
    зап = []
    if os.path.exists(НАХОДКИ):
        for ln in io.open(НАХОДКИ, encoding='utf-8', errors='replace'):
            try:
                зап.append(json.loads(ln))
            except Exception:  # noqa: BLE001
                continue
    # только записи с человеком
    люди = [z for z in зап if (z.get('fio') or z.get('имя') or '').strip()]
    ключи = sorted({k for z in зап[:400] for k in z})

    cx = EDB.EnrichDB().cx
    # в базе центробежников — какие ИНН вообще есть
    инн_базы = set()
    п = os.path.join(ДРОП, 'BAZA-CENTROBEZHNIKI-OBSHCHAYA.csv')
    if os.path.exists(п):
        for r in csv.DictReader(io.StringIO(
                open(п, encoding='utf-8-sig', errors='replace').read()),
                delimiter=';'):
            инн_базы.add((r.get('inn') or '').strip())

    цели = set()
    for r in csv.DictReader(io.StringIO(open(
            os.path.join(ДРОП, 'BEZ-TEHLPR-1486.csv'),
            encoding='utf-8-sig', errors='replace').read()), delimiter=';'):
        цели.add((r.get('inn') or '').strip())

    # люди в enrich.db с техроль по канону, у целевых предприятий
    из_бд = cx.execute(
        "SELECT inn,person,COALESCE(post,''),COALESCE(role,''),"
        "COALESCE(source,''),COALESCE(source_url,'') FROM people").fetchall()
    свои = [r for r in из_бд if r[0] in цели]
    тех_свои = [r for r in свои if r[3] in ТЕХ]
    в_базе = [r for r in тех_свои if r[0] in инн_базы]
    вне = [r for r in тех_свои if r[0] not in инн_базы]

    ист = Counter(r[4][:38] for r in тех_свои)
    примеры_вне = [{'inn': r[0], 'fio': r[1][:34], 'post': r[2][:44],
                    'role': r[3], 'src': r[4][:34]} for r in вне[:10]]

    print(json.dumps({
        'находок_в_jsonl': len(зап), 'из_них_с_человеком': len(люди),
        'ключи_записи': ключи,
        'целевых_ИНН': len(цели),
        'техЛПР_в_enrich_у_целевых': len(тех_свои),
        'из_них_предприятие_есть_в_общей_базе': len(в_базе),
        'из_них_предприятия_НЕТ_в_общей_базе': len(вне),
        'источники_техЛПР': ист.most_common(12),
        'примеры_вне_базы': примеры_вне,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
