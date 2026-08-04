# -*- coding: utf-8 -*-
"""Проставить фактам среду из их СОБСТВЕННОЙ цитаты — вариантом Б.

Дефект нашла 3-я сессия глазами: в цитате факта написано «турбокомпрессора
ВОЗДУШНОГО», а в поле среды пусто или «не названа». Разбор подготовил агент
1-й сессии (`sreda_iz_citaty_wf.py`), он же нашёл две дыры строгого правила и
сделал вариант Б. Здесь ПРИМЕНЯЕТСЯ вариант Б, и вот почему именно он.

ЧИСЛА СУХОГО ПРОГОНА (40 544 факта, среда пуста у 34 153):
    строгое правило   воздух 1093, газ 1529, промахов «газ, а в цитате воздух» 22
    вариант Б         воздух 2478, газ  971
Разница объясняется одним признаком: в строгом правиле «дожимн*» само по себе
считалось газом и дало 586 из 1529 газовых. А «дожимная компрессорная» — это
ИМЯ ЗДАНИЯ, и в цитатах оно стоит рядом с водой и воздухом КИП («Трубопровод
"Вода оборотная II системы в дожимной компрессорной"»). Строгое правило
перевернуло бы 1507 фактов из «наша машина» в «не наша» на ровном месте.
Вариант Б требует рядом с «дожимн» слово газ или ДКС и ловит воздух в любой
форме («Воздух КИП», «Технический воздух» в именительном).

ПРЕДПРИЯТИЙ ЭТО НЕ ПЕРЕКЛАССИФИЦИРУЕТ: в сухом прогоне «предприятий, у которых
меняется вывод» — 0. То есть правка улучшает КАРТОЧКУ (продавец перестаёт
видеть «среда не названа» под цитатой про воздух), а приговоры не трогает.

Пишем ТОЛЬКО туда, где среда пуста или «не названа». Где среда уже названа —
не переписываем: там мог быть разбор сильнее нашего.

По умолчанию СУХОЙ ПРОГОН. Запуск: python sreda_primenit.py [--apply]
"""
import json
import os
import shutil
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r'C:\sender\server\ops')
from sreda_iz_citaty_wf import из_цитаты_б  # noqa: E402  правила варианта Б

БАЗА = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ПРИМЕНИТЬ = '--apply' in sys.argv
ПУСТО = ('', 'не названа', 'среда не названа', 'не установлена', '—', '-')


def main():
    cx = sqlite3.connect(f'file:{БАЗА}?mode=ro', uri=True, timeout=20)
    правки = []
    стат = Counter()
    for rid, ср, цит in cx.execute(
            "SELECT rowid, COALESCE(medium,''), COALESCE(quote,'') FROM fact"):
        если = str(ср).strip().lower()
        if если not in ПУСТО:
            стат['среда уже названа — не трогаем'] += 1
            continue
        нов = из_цитаты_б(цит)
        if not нов:
            стат['цитата молчит'] += 1
            continue
        правки.append((нов, rid))
        стат[f'проставим: {нов}'] += 1
    cx.close()
    print(json.dumps({'к_правке': len(правки), 'разбивка': стат.most_common(),
                      'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой (--apply)'},
                     ensure_ascii=False, indent=1))
    if not ПРИМЕНИТЬ or not правки:
        if not ПРИМЕНИТЬ:
            print('сухой прогон. Повторить с --apply')
        return

    коп = БАЗА + '.bak-' + str(int(time.time()))
    shutil.copy2(БАЗА, коп)
    print(f'бэкап: {os.path.basename(коп)}')
    cx = sqlite3.connect(БАЗА, timeout=120)
    cx.execute('PRAGMA busy_timeout=120000')
    было_пусто = cx.execute(
        "SELECT COUNT(*) FROM fact WHERE COALESCE(medium,'') IN ('','не названа')"
    ).fetchone()[0]
    cx.executemany('UPDATE fact SET medium=? WHERE rowid=?', правки)
    cx.commit()
    стало_пусто = cx.execute(
        "SELECT COUNT(*) FROM fact WHERE COALESCE(medium,'') IN ('','не названа')"
    ).fetchone()[0]
    воздух = cx.execute(
        "SELECT COUNT(*) FROM fact WHERE COALESCE(medium,'') LIKE '%воздух%'"
    ).fetchone()[0]
    газ = cx.execute(
        "SELECT COUNT(*) FROM fact WHERE COALESCE(medium,'') LIKE '%газ%'"
    ).fetchone()[0]
    # контроль: не осталось ли фактов, где среда газ, а цитата говорит воздух
    промах = 0
    for ср, цит in cx.execute(
            "SELECT COALESCE(medium,''), COALESCE(quote,'') FROM fact "
            "WHERE COALESCE(medium,'') LIKE '%газ%'"):
        if из_цитаты_б(цит) == 'воздух':
            промах += 1
    cx.close()
    print(json.dumps({'без_среды_было': было_пусто, 'стало': стало_пусто,
                      'проставлено': было_пусто - стало_пусто,
                      'фактов_со_средой_воздух': воздух,
                      'фактов_со_средой_газ': газ,
                      'КОНТРОЛЬ_газ_но_цитата_воздух': промах},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
