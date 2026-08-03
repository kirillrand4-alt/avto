# -*- coding: utf-8 -*-
"""Скрыть карточки фактов, которые судья назвал мусорными.

Судья возвращает не только приговор по предприятию, но и НОМЕРА фактов: какие
доказывают («fakty_za») и какие к компрессорам отношения не имеют
(«fakty_musor»). Приговор по предприятию применён, а факты — нет, и это
половина дела: продавец открывает карточку доказанного завода и рядом с
настоящим К-250 видит турбокомпрессор КАМАЗа и садовую воздуходувку.

НОМЕР — НЕ ID. Судья отвечает номерами строк карточки, которую я ему показал,
а карточка строится сортировкой фактов по содержательности и обрезается до 22.
Поэтому в приговоре сохранён `fakty_ids` — список id ровно в том порядке, в
каком факты видел судья. Без этой карты «мусорный факт 3» указывает в пустоту:
после любой доливки порядок другой. Приговоры первой версии карты не имели и
пересуживались — здесь берём только версию 2 и выше.

Скрываем, а не удаляем: `centrifugal.db` read-only и пересобирается офлайн,
запись живёт в базе продаж с причиной и автором, возврат одним нажатием.

По умолчанию СУХОЙ ПРОГОН. Запуск: python sud_fakty_musor.py [--apply]
"""
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ПР = os.getenv('CENTRO_SALES_DB') or r'C:\seostat\data\centro_sales.db'
ПРИМЕНИТЬ = '--apply' in sys.argv
КТО = 'admin'

# ЗАЩИТА ОТ СЛИШКОМ УСЕРДНОГО СУДЬИ. Сухой прогон показал, что он относит к
# мусору «Фундамент центробежного нагнетателя поз. В6-6» и «Заключение ЭПБ на
# техническое устройство нагнетатель 400-12-2». Формально он прав: фундамент —
# сооружение, а не машина. Но для продавца это ДОКАЗАТЕЛЬСТВО, что машина на
# заводе есть: фундамент под неё не льют впустую, а заключение ЭПБ выдают на
# конкретное устройство.
#
# Поэтому факт, в тексте которого НАША машина названа прямо, не скрываем,
# даже если судья его забраковал. Цена ошибки несимметрична: спрятанное
# доказательство продавец не найдёт никогда, а лишняя строка ему просто
# мешает — и её он уберёт сам одной кнопкой.
#
# Ровно ту же осторожность соседняя сессия применила к классу «объект —
# трубопровод»: из 190 таких строк около 8% доказывают наличие машины.
_НАША_В_ТЕКСТЕ = re.compile(
    r'центробежн|турбовоздуходувк|турбокомпрессор|нагнетател|'
    r'\bцк[\s-]?\d|\bк-?\d{3}-\d{2}|\b\d{2}вц[\s-]?\d|компрессорн\w*\s+станц',
    re.I)


def main():
    db = EDB.EnrichDB()
    строки = list(db.cx.execute(
        'SELECT inn, verdikt, COALESCE(fakty_musor,\'[]\'), '
        'COALESCE(fakty_ids,\'[]\') FROM sud_centro '
        'WHERE COALESCE(versiya,1) >= 2'))
    цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
    факты = {}
    for и, ид, м, т, ц in цб.execute(
            "SELECT inn, id, COALESCE(model,''), COALESCE(equipment_type,''), "
            "COALESCE(quote,'') FROM fact"):
        факты[int(ид)] = (str(и), м, т, ц)
    цб.close()

    пр = sqlite3.connect(ПР, timeout=20)
    пр.execute('PRAGMA busy_timeout=20000')
    пр.executescript(
        'CREATE TABLE IF NOT EXISTS hidden_item('
        'id INTEGER PRIMARY KEY, inn TEXT NOT NULL, kind TEXT NOT NULL, '
        'value TEXT NOT NULL, reason TEXT, username TEXT, created_at TEXT, '
        'UNIQUE(inn, kind, value));')
    уже = {(str(r[0]), str(r[1])) for r in
           пр.execute("SELECT inn, value FROM hidden_item WHERE kind='fact'")}

    к_скрытию = []
    вне_карты = 0
    без_карты = 0
    по_вердикту = Counter()
    спасено = Counter()
    примеры = []
    for инн, вердикт, сыр_м, сыр_ид in строки:
        try:
            номера = [int(x) for x in json.loads(сыр_м or '[]')]
            иды = [int(x) for x in json.loads(сыр_ид or '[]')]
        except Exception:  # noqa: BLE001
            continue
        if not номера:
            continue
        if not иды:
            без_карты += 1
            continue
        for н in номера:
            # судья нумерует с 1; всё, что вне длины карты, — его ошибка,
            # и молча её проглатывать нельзя
            if not (1 <= н <= len(иды)):
                вне_карты += 1
                continue
            ид = иды[н - 1]
            св = факты.get(ид)
            if not св or св[0] != инн:
                вне_карты += 1
                continue
            if (инн, str(ид)) in уже:
                continue
            if _НАША_В_ТЕКСТЕ.search(f'{св[1]} {св[2]} {св[3]}'):
                спасено[(св[1] or св[2] or 'без марки')[:40]] += 1
                continue
            по_вердикту[вердикт] += 1
            к_скрытию.append((инн, str(ид), вердикт, св[1], св[2], св[3]))
            if len(примеры) < 10:
                примеры.append({'inn': инн, 'id': ид, 'марка': св[1][:34],
                                'тип': св[2][:30], 'цитата': св[3][:80]})

    print(json.dumps({
        'приговоров_версии_2': len(строки),
        'из_них_без_карты_позиций': без_карты,
        'ФАКТОВ_К_СКРЫТИЮ': len(к_скрытию),
        'номеров_мимо_карты_ошибка_судьи': вне_карты,
        'по_приговору_предприятия': по_вердикту.most_common(),
        'НЕ_СКРЫТО_наша_машина_названа_в_тексте': sum(спасено.values()),
        'что_спасено': спасено.most_common(8),
        'уже_скрыто_фактов_ранее': len(уже),
        'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой (--apply)',
    }, ensure_ascii=False, indent=1))
    for э in примеры:
        print(f'  {э["inn"]} факт {э["id"]}: [{э["марка"] or "без марки"}] '
              f'{э["тип"]} — {э["цитата"]}')

    if not ПРИМЕНИТЬ or not к_скрытию:
        if not ПРИМЕНИТЬ:
            print('\nсухой прогон. Повторить с --apply')
        пр.close()
        return
    сейчас = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    пр.executemany(
        'INSERT OR REPLACE INTO hidden_item'
        '(inn, kind, value, reason, username, created_at) VALUES(?,?,?,?,?,?)',
        [(и, 'fact', ид,
          f'суд моделей: к компрессорам не относится ({(мар or тип or "без марки")[:60]})'[:200],
          КТО, сейчас) for и, ид, _в, мар, тип, _ц in к_скрытию])
    пр.commit()
    стало = пр.execute(
        "SELECT COUNT(*) FROM hidden_item WHERE kind='fact'").fetchone()[0]
    пр.close()
    цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
    всего = цб.execute('SELECT COUNT(*) FROM fact').fetchone()[0]
    цб.close()
    print(json.dumps({'скрыто_фактов_всего': стало, 'фактов_в_базе': всего,
                      'видимых_фактов': всего - стало}, ensure_ascii=False))


if __name__ == '__main__':
    main()
