# -*- coding: utf-8 -*-
"""P25: снять спорные привязки почт по файлу 3-й сессии (обратный ход 001–008).

ЧТО СЛУЧИЛОСЬ У НЕЁ. На страницах «контакты службы снабжения» люди идут
списком, и ближайший к фамилии адрес почти никогда не принадлежит тому, кого
искали: `Взыграев → Nikolay.Zaretsky@`, `Бергер → KukarinaAV@`. Её канал это
РАСПОЗНАВАЛ и подписывал `uverennost='спорная'`, а выкладка поле уверенности не
читала. Заслон был, его никто не спрашивал.

ЧТО ЭТО ЗНАЧИТ ДЛЯ МЕНЯ. Обратный ход 002–007 я влил ДО её предупреждения.
Снимаю привязки по её ключу «ИНН + человек + значение контакта».

СНИМАЮ ПРИВЯЗКУ, А НЕ КОНТАКТ. Адрес настоящий и предприятию принадлежит —
ложным было имя рядом с ним. Поэтому `person` очищается, ставится
`is_unknown_owner=1` и причина, а сам контакт остаётся. Это правило владельца
«разделять, а не отсеивать»: выбросить адрес значит потерять то, что добыто
верно.

НАБЛЮДЕНИЯ НЕ ТРОГАЮ. В `contact_source` записано, что мы ВИДЕЛИ на странице, и
это правда; неправдой был вывод из увиденного.

Запуск: python p25_snyat_spornye.py <файл-спорных.csv> [--apply]
"""
import csv
import io
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter

P25 = r'C:\seostat\data\p25.db'
ОБМЕН = r'C:\seostat\drop\drop-storage'
ПОТОК = r'C:\seostat\drop\p25_snyatye_privyazki.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv
ИМЯ = next((а for а in sys.argv[1:] if а.lower().endswith('.csv')), '')


def чисто(з):
    return ' '.join(str(з or '').split())


def main():
    путь = os.path.join(ОБМЕН, ИМЯ)
    if not ИМЯ or not os.path.exists(путь):
        print('нужен файл спорных на дропе:', путь or '(имя не задано)')
        return
    сыр = io.open(путь, encoding='utf-8-sig', errors='replace').read()
    первая = сыр.splitlines()[0] if сыр.strip() else ''
    раздел = ';' if первая.count(';') >= первая.count(',') else ','
    строки = list(csv.DictReader(io.StringIO(сыр), delimiter=раздел))
    print(f'файл {ИМЯ}: строк {len(строки)}')

    цели = set()
    for р in строки:
        инн = re.sub(r'\D', '', str(р.get('inn') or ''))
        чел = чисто(р.get('chelovek'))
        for к in ('pochta', 'telefon'):
            зн = чисто(р.get(к)).lower()
            if инн and чел and зн:
                цели.add((инн, чел.casefold(), зн))
    print(f'ключей «ИНН + человек + контакт»: {len(цели)}')

    цб = sqlite3.connect(P25, timeout=30)
    поля = {r[1] for r in цб.execute('PRAGMA table_info(contact)')}
    к_снятию = []
    for rid, инн, чел, зн, вид in цб.execute(
            "SELECT rowid, inn, COALESCE(person,''), COALESCE(value,''), "
            "COALESCE(kind,'') FROM contact WHERE COALESCE(person,'')<>''"):
        ключ = (str(инн), чисто(чел).casefold(), чисто(зн).lower())
        if ключ in цели:
            к_снятию.append((rid, str(инн), чисто(чел), чисто(зн), вид))

    стат = Counter()
    стат['в файле спорных строк'] = len(строки)
    стат['НАЙДЕНО В БАЗЕ, привязка будет снята'] = len(к_снятию)
    for _rid, _и, _ч, _з, вид in к_снятию:
        стат[f'   вид: {вид}'] += 1

    print()
    print('ПРИВЯЗКИ К СНЯТИЮ (контакт остаётся, уходит имя рядом с ним):')
    for _rid, инн, чел, зн, _в in к_снятию[:10]:
        print(f'   {инн} {чел[:28]:28} ← {зн[:40]}')
    if not к_снятию:
        print('   ни одной — из спорных в базу ничего не попало')

    if not ПРИМЕНИТЬ or not к_снятию:
        print()
        print(json.dumps(dict(стат.most_common()), ensure_ascii=False, indent=1))
        print('СУХОЙ ПРОГОН' if not ПРИМЕНИТЬ else 'снимать нечего')
        цб.close()
        return

    ts = time.strftime('%Y-%m-%dT%H:%M:%S')
    журнал = []
    снято = 0
    for rid, инн, чел, зн, вид in к_снятию:
        куски = ["person=''"]
        if 'is_unknown_owner' in поля:
            куски.append('is_unknown_owner=1')
        if 'chem_podtverzhdena' in поля:
            куски.append("chem_podtverzhdena='привязка снята: канал 3-й сессии "
                         "отметил её спорной (адрес другого сотрудника рядом)'")
        try:
            цб.execute(f"UPDATE contact SET {', '.join(куски)} WHERE rowid=?", (rid,))
            снято += 1
        except sqlite3.IntegrityError:
            цб.execute('DELETE FROM contact WHERE rowid=?', (rid,))
            стат['строка-близнец без имени уже была, удалена'] += 1
        журнал.append({'inn': инн, 'byl_chelovek': чел, 'kontakt': зн,
                       'kind': вид, 'ts': ts})
    цб.commit()
    всего = цб.execute('SELECT COUNT(*) FROM contact').fetchone()[0]
    людей = цб.execute('SELECT COUNT(*) FROM person').fetchone()[0]
    набл = цб.execute('SELECT COUNT(*) FROM contact_source').fetchone()[0]
    цб.close()

    with io.open(ПОТОК, 'a', encoding='utf-8') as ф:
        for з in журнал:
            ф.write(json.dumps(з, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())

    print()
    print(json.dumps(dict(стат.most_common()), ensure_ascii=False, indent=1))
    print(f'привязок снято: {снято}')
    print(f'СТАЛО: контактов {всего} | людей {людей} | наблюдений {набл}')


if __name__ == '__main__':
    main()
