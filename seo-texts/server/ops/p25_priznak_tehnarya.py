# -*- coding: utf-8 -*-
"""P25: признак технаря — по ДОЛЖНОСТИ, а не по словам входного файла.

ЧТО СЛОМАНО И КАК НАШЛОСЬ. Проверяя находку 3-й сессии про слепоту SQL к
кириллице, я замерил у себя людей с «главный инженер / энергетик / механик» в
должности и посмотрел, стоит ли у них признак технаря. На центробежке стоит у
всех 1 642 — там роль канонизируется питоном. В P25 — не у всех: `Чучкалов
Владимир Юрьевич, Главный инженер` признака НЕ имел.

ПРИЧИНА НЕ В КИРИЛЛИЦЕ. Моя приёмка ставила `is_tech` по словам роли из ФАЙЛА
(«1 круг», «2 круг»), а соседние заливки писали роль иначе — «техническая».
Слово другое, человек тот же. То есть признак зависел от лексики автора файла,
а не от того, кто этот человек. Это моя ошибка: заслон должен смотреть на
должность, а входные слова принимать как подсказку, не как источник истины.

ЛЕЧУ ДВУМЯ ПУТЯМИ СРАЗУ, ОБА ПИТОНОВСКИЕ:
  * должность через `EnrichDB._canon_role` — тот же канон, что на центробежке
    (он уже знает «начальник ЛЮБОГО цеха» и десятки живых подписей);
  * роль — по вхождению «1 круг / 2 круг / техническ» в нижнем регистре.
Признак СНИМАТЬ не буду ни у кого: поставлен он мог быть по знанию, которого в
этих двух полях нет, а снятие — потеря. Только доставляю.

Запуск: python p25_priznak_tehnarya.py [--apply]
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

P25 = r'C:\seostat\data\p25.db'
ПОТОК = r'C:\seostat\drop\p25_priznak_tehnarya.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv
# На сервере лежит отставшая копия enrich_db.py — `TECH_ROLES` в ней ещё нет.
# Берём из модуля, если есть, иначе тот же список из репозитория.
_ТЕХ_ЗАПАС = ('гл.инженер', 'гл.энергетик', 'гл.механик', 'гл.технолог',
              'гл.конструктор', 'техдиректор', 'нач.производства',
              'нач.цеха', 'АСУ/КИПиА')
ТЕХ_КАНОН = set(getattr(EDB.EnrichDB, 'TECH_ROLES', _ТЕХ_ЗАПАС)) | {'техконтакт'}
ТЕХ_СЛОВА = ('1 круг', '2 круг', 'техническ')


def технарь(должность, роль):
    """Вернуть причину, по которой человек технический, или пустую строку."""
    низ_роль = str(роль or '').lower()
    for с in ТЕХ_СЛОВА:
        if с in низ_роль:
            return f'роль: {с}'
    try:
        канон = EDB.EnrichDB._canon_role(должность) or ''
    except Exception:  # noqa: BLE001
        канон = ''
    if канон in ТЕХ_КАНОН:
        return f'должность → {канон}'
    return ''


def main():
    цб = sqlite3.connect(P25, timeout=30)
    стат = Counter()
    правки = {'person': [], 'contact': []}
    примеры = []

    for табл in ('person', 'contact'):
        поля = {r[1] for r in цб.execute(f'PRAGMA table_info({табл})')}
        if not {'is_tech', 'position', 'role'} <= поля:
            стат[f'{табл}: нет нужных колонок'] += 1
            continue
        для_имени = 'person' if 'person' in поля else 'value'
        for rid, кто, пост, роль, тех in цб.execute(
                f"SELECT rowid, COALESCE({для_имени},''), COALESCE(position,''), "
                f"COALESCE(role,''), COALESCE(is_tech,0) FROM {табл}"):
            причина = технарь(пост, роль)
            if причина and not тех:
                правки[табл].append((rid, причина))
                стат[f'{табл}: ДОСТАВИТЬ признак'] += 1
                if len(примеры) < 12:
                    примеры.append(f'{табл:8} {str(кто)[:26]:26} {пост[:26]:26} '
                                   f'роль={роль[:16]:16} ← {причина}')
            elif тех:
                стат[f'{табл}: признак уже стоял'] += 1

    print('КОМУ ДОСТАВЛЯЮ ПРИЗНАК ТЕХНАРЯ:')
    for п in примеры:
        print('   ', п)
    if not примеры:
        print('    никому — признак у всех на месте')

    if not ПРИМЕНИТЬ:
        print()
        print(json.dumps(dict(стат.most_common()), ensure_ascii=False, indent=1))
        print('СУХОЙ ПРОГОН, ничего не изменено')
        цб.close()
        return

    ts = time.strftime('%Y-%m-%dT%H:%M:%S')
    журнал = []
    for табл, список in правки.items():
        for rid, причина in список:
            цб.execute(f'UPDATE {табл} SET is_tech=1 WHERE rowid=?', (rid,))
            журнал.append({'табл': табл, 'rowid': rid, 'причина': причина, 'ts': ts})
    цб.commit()

    людей_тех = цб.execute(
        'SELECT COUNT(*) FROM person WHERE COALESCE(is_tech,0)=1').fetchone()[0]
    предприятий = цб.execute(
        'SELECT COUNT(DISTINCT inn) FROM person WHERE COALESCE(is_tech,0)=1').fetchone()[0]
    цб.close()

    with io.open(ПОТОК, 'a', encoding='utf-8') as ф:
        for з in журнал:
            ф.write(json.dumps(з, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())

    print()
    print(json.dumps(dict(стат.most_common()), ensure_ascii=False, indent=1))
    print(f'ТЕХНИЧЕСКИХ ЛЮДЕЙ В P25: {людей_тех} на {предприятий} предприятиях из 491')


if __name__ == '__main__':
    main()
