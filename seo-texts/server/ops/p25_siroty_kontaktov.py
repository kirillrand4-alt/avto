# -*- coding: utf-8 -*-
"""P25: контакты, приписанные человеку, которого в базе больше нет.

ЗАЧЕМ. Гигиена убрала из `person` строку «Уважаемый Сергей Владимирович» —
обращение из письма, принятое за фамилию. Но продавец смотрит не в `person`, а в
КОНТАКТЫ карточки, и там приписка могла остаться. Удалять её нельзя: номер
настоящий, ложным было только имя рядом с ним.

ЧТО ДЕЛАЮ. Контакту, у которого имя не находится среди людей предприятия,
чищу поле человека и ставлю честное «чей — не установлено»:
`person=''`, `phone_type='общий'`, `is_unknown_owner=1`. Наблюдение в
`contact_source` не трогаю: там записано, что мы видели, и это было правдой.

Запуск: python p25_siroty_kontaktov.py [--apply]
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter

P25 = r'C:\seostat\data\p25.db'
ПОТОК = r'C:\seostat\drop\p25_siroty_kontaktov.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv


def main():
    цб = sqlite3.connect(P25, timeout=30)
    люди = set()
    for инн, ч in цб.execute("SELECT inn, COALESCE(person,'') FROM person"):
        люди.add((str(инн), ' '.join(str(ч).split()).casefold()))

    сироты = []
    for rid, инн, вид, зн, ч in цб.execute(
            "SELECT rowid, inn, COALESCE(kind,''), COALESCE(value,''), "
            "COALESCE(person,'') FROM contact WHERE COALESCE(person,'')<>''"):
        if (str(инн), ' '.join(str(ч).split()).casefold()) not in люди:
            сироты.append((rid, str(инн), вид, зн, ч))

    стат = Counter()
    for _rid, _и, вид, _з, _ч in сироты:
        стат[f'сирот: {вид}'] += 1

    print('КОНТАКТЫ С ИМЕНЕМ, КОТОРОГО НЕТ СРЕДИ ЛЮДЕЙ ПРЕДПРИЯТИЯ:')
    for rid, инн, вид, зн, ч in сироты[:12]:
        print(f'   {инн} {вид:6} {зн[:24]:24} приписан: {ч[:36]}')
    if not сироты:
        print('    ни одного — приписки чистые')

    if not ПРИМЕНИТЬ or not сироты:
        print()
        print(json.dumps(dict(стат.most_common()), ensure_ascii=False, indent=1))
        print('СУХОЙ ПРОГОН' if not ПРИМЕНИТЬ else 'нечего чинить')
        цб.close()
        return

    ts = time.strftime('%Y-%m-%dT%H:%M:%S')
    поля = {r[1] for r in цб.execute('PRAGMA table_info(contact)')}
    журнал = []
    убрано = 0
    for rid, инн, вид, зн, ч in сироты:
        куски = ["person=''"]
        if 'phone_type' in поля and вид == 'phone':
            куски.append("phone_type='общий'")
        if 'is_unknown_owner' in поля:
            куски.append('is_unknown_owner=1')
        if 'chem_podtverzhdena' in поля:
            куски.append("chem_podtverzhdena='приписка снята: имя не человек'")
        try:
            цб.execute(f"UPDATE contact SET {', '.join(куски)} WHERE rowid=?", (rid,))
            убрано += 1
        except sqlite3.IntegrityError:
            # такой же контакт без имени уже есть — эта строка лишняя
            цб.execute('DELETE FROM contact WHERE rowid=?', (rid,))
            стат['строка-близнец уже была, удалена'] += 1
        журнал.append({'inn': инн, 'kind': вид, 'value': зн, 'byla_pripiska': ч,
                       'ts': ts})
    цб.commit()
    всего = цб.execute('SELECT COUNT(*) FROM contact').fetchone()[0]
    безымянных = цб.execute(
        "SELECT COUNT(*) FROM contact WHERE COALESCE(person,'')=''").fetchone()[0]
    цб.close()

    with io.open(ПОТОК, 'a', encoding='utf-8') as ф:
        for з in журнал:
            ф.write(json.dumps(з, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())

    print()
    print(json.dumps(dict(стат.most_common()), ensure_ascii=False, indent=1))
    print(f'приписок снято: {убрано}')
    print(f'КОНТАКТОВ ВСЕГО {всего}, из них без имени {безымянных}')


if __name__ == '__main__':
    main()
