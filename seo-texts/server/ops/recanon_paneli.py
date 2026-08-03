# -*- coding: utf-8 -*-
"""Пересчёт ролей по действующему канону В БАЗЕ ПАНЕЛИ, а не только в enrich.db.

НАЙДЕНО ОБРАТНЫМ АУДИТОМ (пункт 16 владельца). `recanon_roles.py` пересчитывает
роли в `enrich.db` и на этом останавливается. Панель хранит СВОЮ копию: роль и
`is_tech` попадают в `centrifugal.db` в момент заливки и потом живут сами по
себе. База панели собрана 02.08 в 17:03, канон правился 02.08 в 19:17 — то есть
роли у продавца на два часа старше канона, а пересборку мы сознательно не
делаем (она стоила бы 210 предприятий и двух тысяч людей).

ПОЧЕМУ ЭТО НЕ КОСМЕТИКА. Канон правился ровно потому, что голые ключи
«инженер» и «техни» делали главного инженера из метролога, дежурного инженера
и инженера-электрика: 56 случаев из 90. А карточка панели сортирует людей
`ORDER BY COALESCE(is_tech,0) DESC` — значит именно эти 56 стоят ПЕРВЫМИ, выше
настоящих главных инженеров. Продавец звонит сверху вниз и делает вывод о
качестве всей базы по первым же звонкам не тем людям.

Пересчитываем из `position` — текст должности в панели сохранён, поэтому роль
выводится без единого похода в сеть.

ТЕЛЕФОНЫ ТРОГАЕМ ОСТОРОЖНО. В `contact.role` лежит не всегда должность: у
номеров там бывает метка источника («приёмная», «диспетчерская», «контакты
компании»). Пересчитываем только те, где заполнен `position` — он приходит
именно из должности человека.

По умолчанию СУХОЙ ПРОГОН и режим «только техЛПР»: применяются лишь строки,
где меняется САМ ответ «технический ЛПР или нет». Пересчёт всего подряд тащит
и побочные ухудшения канона (живой пример из enrich.db: «Руководитель службы
маркетинга» из «продажи» становится «директор»), и делать это заодно, молча,
нельзя.

Запуск: python recanon_paneli.py [--apply] [--vse-roli]
"""
import json
import os
import shutil
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

БАЗА = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ПРИМЕНИТЬ = '--apply' in sys.argv
ВСЕ_РОЛИ = '--vse-roli' in sys.argv
ТЕХ = set(EDB.EnrichDB.TECH_ROLES) | {'техконтакт'}


def канон(должность):
    try:
        return EDB.EnrichDB._canon_role(должность) or ''
    except Exception:  # noqa: BLE001
        return ''


def main():
    cx = sqlite3.connect(f'file:{БАЗА}?mode=ro', uri=True, timeout=20)
    люди = list(cx.execute(
        "SELECT id, inn, COALESCE(person,''), COALESCE(position,''), "
        "COALESCE(role,''), COALESCE(is_tech,0) FROM person"))
    колонки = {c[1] for c in cx.execute('PRAGMA table_info("contact")')}
    контакты = []
    if {'position', 'role', 'is_tech'} <= колонки:
        контакты = list(cx.execute(
            "SELECT id, COALESCE(position,''), COALESCE(role,''), "
            "COALESCE(is_tech,0) FROM contact WHERE COALESCE(position,'')<>''"))
    cx.close()

    менять_л, менять_к = [], []
    пары = Counter()
    теряют_тех, получают_тех = 0, 0
    без_должности = sum(1 for _i, _и, _ч, п, _р, _т in люди if not есть_текст(п))
    for ид, инн, чел, пост, роль, тех in люди:
        if not пост.strip():
            continue
        нов = канон(пост)
        if not нов:
            continue
        нов_тех = 1 if нов in ТЕХ else 0
        if нов == роль and нов_тех == тех:
            continue
        меняет_ответ = (нов_тех != тех)
        if меняет_ответ:
            (теряют_тех, получают_тех) = (
                (теряют_тех + 1, получают_тех) if тех and not нов_тех
                else (теряют_тех, получают_тех + 1))
        if not (ВСЕ_РОЛИ or меняет_ответ):
            continue
        пары[f'{роль or "пусто"} → {нов}'] += 1
        менять_л.append((нов, нов_тех, ид, чел, пост, роль, инн))

    for ид, пост, роль, тех in контакты:
        нов = канон(пост)
        if not нов:
            continue
        нов_тех = 1 if нов in ТЕХ else 0
        if нов == роль and нов_тех == тех:
            continue
        if not (ВСЕ_РОЛИ or нов_тех != тех):
            continue
        менять_к.append((нов, нов_тех, ид))

    print(json.dumps({
        'людей_в_панели': len(люди),
        'из_них_с_должностью': sum(1 for x in люди if x[3].strip()),
        'БЕЗ_должности_пересчитать_нечем': без_должности,
        'людей_к_правке': len(менять_л),
        'из_них_ТЕРЯЮТ_техЛПР': теряют_тех,
        'из_них_ПОЛУЧАЮТ_техЛПР': получают_тех,
        'контактов_к_правке': len(менять_к),
        'переходы': пары.most_common(14),
        'режим': ('ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой (--apply)')
                 + (', все роли' if ВСЕ_РОЛИ else ', только меняющие ответ техЛПР'),
    }, ensure_ascii=False, indent=1))
    for нов, нов_тех, _ид, чел, пост, роль, инн in менять_л[:10]:
        print(f'  {инн} {чел[:26]:<26} «{пост[:40]}» {роль or "пусто"} → '
              f'{нов} (техЛПР {"да" if нов_тех else "нет"})')

    if not ПРИМЕНИТЬ or not (менять_л or менять_к):
        if not ПРИМЕНИТЬ:
            print('\nсухой прогон. Повторить с --apply')
        return

    коп = БАЗА + '.bak-' + str(int(time.time()))
    shutil.copy2(БАЗА, коп)
    print(f'копия базы: {os.path.basename(коп)}')
    зп = sqlite3.connect(БАЗА, timeout=60)
    try:
        зп.executemany('UPDATE person SET role=?, is_tech=? WHERE id=?',
                       [(н, т, и) for н, т, и, *_ in менять_л])
        if менять_к:
            зп.executemany('UPDATE contact SET role=?, is_tech=? WHERE id=?',
                           менять_к)
        зп.commit()
    finally:
        зп.close()

    # числа ПЕРЕЧИТЫВАНИЕМ базы
    cx = sqlite3.connect(f'file:{БАЗА}?mode=ro', uri=True, timeout=20)
    тех_л = cx.execute('SELECT COUNT(*) FROM person WHERE is_tech=1').fetchone()[0]
    предпр = cx.execute(
        'SELECT COUNT(DISTINCT inn) FROM person WHERE is_tech=1').fetchone()[0]
    cx.close()
    print(json.dumps({'технических_людей_в_панели_стало': тех_л,
                      'предприятий_с_техЛПР': предпр}, ensure_ascii=False))


def есть_текст(т):
    """Непустой текст. Отдельной функцией, потому что «нет должности» и
    «должность есть, но канон её не берёт» — разные случаи, и путать их
    нельзя: первое лечится добором должности, второе правкой канона."""
    return bool(str(т or '').strip())


if __name__ == '__main__':
    main()
