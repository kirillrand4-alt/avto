# -*- coding: utf-8 -*-
"""Откуда в карточке «Источники проверки компании: ZHURNAL-2 (ветка claude ...)».

ПОЧЕМУ ОТДЕЛЬНАЯ ПРОВЕРКА. По `fact.source` таких строк НОЛЬ — то есть моя первая догадка
о том, где лежит мусор, была неверной, и остановись я на ней, получилось бы «дефекта нет»
при дефекте, который видно на экране. Значит поле другое: в `company` есть
`istochnik_rekvizitov` и `ssylki_na_istochniki`. Смотрю их.
"""
import json
import sqlite3

cx = sqlite3.connect(r'C:\seostat\data\centrifugal.db')
o = {}
for pole in ('istochnik_rekvizitov', 'ssylki_na_istochniki', 'istochnik_dopolneniya'):
    try:
        o[f'{pole}_всего_непустых'] = cx.execute(
            f'select count(*) from company where coalesce("{pole}",\'\') <> \'\'').fetchone()[0]
        o[f'{pole}_топ'] = cx.execute(
            f'select substr(coalesce("{pole}",\'\'),1,90), count(*) from company '
            f'where coalesce("{pole}",\'\') <> \'\' group by 1 order by 2 desc limit 6'
        ).fetchall()
        o[f'{pole}_похоже_на_журнал'] = cx.execute(
            f'select count(*) from company where lower(coalesce("{pole}",\'\')) like \'%zhurnal%\' '
            f'or lower(coalesce("{pole}",\'\')) like \'%claude%\' '
            f'or lower(coalesce("{pole}",\'\')) like \'%ветка%\'').fetchone()[0]
    except Exception as e:  # noqa: BLE001
        o[pole] = f'{type(e).__name__}: {e}'
print(json.dumps(o, ensure_ascii=False, indent=1))
