# -*- coding: utf-8 -*-
"""Происхождение сайта хранить в базе, а не восстанавливать задним числом.

ЧТО ВСКРЫЛОСЬ. Сверка напечатала «СОВПАЛО — подтверждено двумя источниками 222».
Заслон «ТОЛЬКО ЧЕКО (мой же залив)» в ней был, но спросить его было не у чего:
колонки `istochnik_sayta` в p25.db нет, источник читался как пустая строка, и
условие `'чеко' in ист` не сработало ни разу. Проверка по потоку залива
`sayty_iz_cheko.jsonl` (413 записей по P25) даёт настоящий расклад:

    мой же залив из чеко, один источник      193
    честное совпадение (соседки + чеко)       29

Это ровно тот случай, за который мы ловим друг друга всю смену: ярлык говорит
«подтверждено дважды», а под ним один источник, посчитанный за два.

ЧТО ДЕЛАЕТ ЭТОТ ХОД
  1. Заводит колонку `istochnik_sayta` — чтобы происхождение жило в базе.
  2. Заполняет её по потоку залива (durable-запись на сервере, не по памяти).
  3. Ставит «подтверждён дважды» ТОЛЬКО тем, кого нашли соседки и совпало с чеко.
  4. Переписывает файл расхождений, отделяя находки соседок от моих же заливов.

Запуск: python sayty_provenans.py [--apply]
"""
import csv, io, json, os, re, sqlite3, sys, time
from collections import Counter
sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB

P25 = r'C:\seostat\data\p25.db'
ПОТОК = r'C:\seostat\drop\sayty_iz_cheko.jsonl'
ВЫХОД = r'C:\seostat\drop\drop-storage\P25-SAYTY-RASHOZHDENIYA-1S.csv'
ПРИМЕНИТЬ = '--apply' in sys.argv


def домен(з):
    д = str(з or '').strip().lower()
    д = re.sub(r'^https?://', '', д)
    д = re.sub(r'^www\.', '', д).split('/')[0].split('?')[0].strip()
    return д if re.match(r'^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$', д) else ''


мой_залив = {}
if os.path.exists(ПОТОК):
    for стр in io.open(ПОТОК, encoding='utf-8', errors='replace'):
        стр = стр.strip()
        if not стр:
            continue
        try:
            з = json.loads(стр)
        except Exception:
            continue
        if str(з.get('baza') or '') in ('P25', 'p25'):
            мой_залив[str(з.get('inn'))] = домен(з.get('domen'))

db = EDB.EnrichDB()
чеко = {}
for и, с in db.cx.execute("SELECT inn, COALESCE(site_checko,'') FROM companies "
                          "WHERE COALESCE(site_checko,'')<>''"):
    д = домен(с)
    if д:
        чеко[str(и)] = д

цб = sqlite3.connect(P25, timeout=30)
поля = {r[1] for r in цб.execute('PRAGMA table_info(company)')}
if 'istochnik_sayta' not in поля:
    if ПРИМЕНИТЬ:
        цб.execute('ALTER TABLE company ADD COLUMN istochnik_sayta TEXT')
        цб.commit()
        поля.add('istochnik_sayta')
        print('колонка istochnik_sayta заведена')
    else:
        print('колонки istochnik_sayta нет — будет заведена при --apply')

стат = Counter()
пометки = []
расхождения = []
для_залива = []
for и, с, имя in цб.execute(
        "SELECT inn, COALESCE(sayt,''), COALESCE(predpriyatie,'') FROM company"):
    и, наш, имя = str(и), домен(с), str(имя)
    ч = чеко.get(и, '')
    мой = мой_залив.get(и, '')
    if not наш and not ч:
        стат['сайта нет ни у кого'] += 1
    elif ч and not наш:
        стат['есть у чеко, у нас пусто — залить'] += 1
        для_залива.append((и, ч))
    elif наш and not ч:
        откуда = ('чеко: карточка компании (чеко больше не отдаёт)' if мой == наш
                  else 'поиск соседних сессий, один источник')
        стат['мой залив из чеко, чеко теперь молчит' if мой == наш
             else 'нашли соседки, чеко не знает — один источник'] += 1
        пометки.append((и, откуда))
    elif наш == ч:
        if мой == наш:
            стат['ТОЛЬКО ЧЕКО: мой же залив, это один источник'] += 1
            пометки.append((и, 'чеко: карточка компании (единственный источник)'))
        else:
            стат['ПОДТВЕРЖДЕНО ДВАЖДЫ: нашли соседки, чеко совпало'] += 1
            пометки.append((и, 'подтверждён дважды: поиск + карточка чеко'))
    else:
        чей = ('мой залив из чеко разошёлся с текущей карточкой чеко'
               if мой == наш else 'находка соседних сессий')
        стат['РАЗОШЛОСЬ: находка соседок против карточки чеко'
             if мой != наш else
             'РАЗОШЛОСЬ: мой залив против свежей карточки чеко'] += 1
        расхождения.append({'inn': и, 'predpriyatie': имя[:60],
                            'u_nas': наш, 'u_cheko': ч, 'chey_nash': чей})

print()
for к, v in sorted(стат.items()):
    print(f'{к:56} {v:5}')

if not ПРИМЕНИТЬ:
    print()
    print('СУХОЙ ПРОГОН: ничего не записано, файл не переписан')
    цб.close()
    raise SystemExit

for и, откуда in пометки:
    цб.execute('UPDATE company SET istochnik_sayta=? WHERE inn=?', (откуда, и))
for и, ч in для_залива:
    цб.execute("UPDATE company SET sayt=?, istochnik_sayta=? WHERE inn=? "
               "AND COALESCE(sayt,'')=''",
               (ч, 'чеко: карточка компании (единственный источник)', и))
цб.commit()

соседки = [з for з in расхождения if з['chey_nash'] == 'находка соседних сессий']
with io.open(ВЫХОД, 'w', encoding='utf-8-sig', newline='') as ф:
    п = csv.DictWriter(ф, fieldnames=['inn', 'predpriyatie', 'u_nas', 'u_cheko',
                                      'chey_nash'], delimiter=';')
    п.writeheader()
    п.writerows(расхождения)
    ф.flush()
    os.fsync(ф.fileno())

с_сайтом = цб.execute("SELECT COUNT(*) FROM company "
                      "WHERE COALESCE(sayt,'')<>''").fetchone()[0]
всего = цб.execute('SELECT COUNT(*) FROM company').fetchone()[0]
без_метки = цб.execute("SELECT COUNT(*) FROM company WHERE COALESCE(sayt,'')<>'' "
                       "AND COALESCE(istochnik_sayta,'')=''").fetchone()[0]
цб.close()

print()
print(f'происхождение проставлено строкам        {len(пометки):5}')
print(f'долито из чеко в пустые клетки           {len(для_залива):5}')
print(f'в файле расхождений строк                {len(расхождения):5}')
print(f'   из них находки соседок (им и слать)   {len(соседки):5}')
print(f'сайт есть у                              {с_сайтом:5} из {всего}')
print(f'сайт есть, а происхождение неизвестно    {без_метки:5}')
