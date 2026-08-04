# -*- coding: utf-8 -*-
"""Двойное подтверждение сайтов: карточка ИНН на чеко против находки соседок.

Замечание владельца: сайт из чеко нужен и там, где клетка уже занята — тогда
домен, найденный соседками по выдаче, получает ВТОРОЙ независимый источник.
Раньше я писал только в пустую клетку и остальное выбрасывал.

Три исхода, и каждый — отдельное действие:
  СОВПАЛО     принадлежность доказана дважды: карточкой ИНН и поиском.
              Вопрос закрыт, помечаем.
  РАЗОШЛОСЬ   находка соседок под вопросом. НЕ переписываю их значение молча:
              отдаю файлом, пусть посмотрят — у них есть цитата и вес, у меня
              только карточка агрегатора.
  ТОЛЬКО ЧЕКО клетка была пуста, залито мной ранее — это не подтверждение,
              а единственный источник. Считаю отдельно, чтобы не путать.

Сравниваю ДОМЕНЫ, а не строки: `https://www.zavod.ru/` и `zavod.ru` — одно и
то же, и такая мелочь легко превратила бы совпадение в расхождение.

Запуск: python sverka_saytov_cheko.py [--apply]
"""
import csv, io, json, os, re, sqlite3, sys, time
from collections import Counter
sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB

P25 = r'C:\seostat\data\p25.db'
ВЫХОД = r'C:\seostat\drop\drop-storage\P25-SAYTY-RASHOZHDENIYA-1S.csv'
ПРИМЕНИТЬ = '--apply' in sys.argv

def домен(з):
    д = str(з or '').strip().lower()
    д = re.sub(r'^https?://', '', д)
    д = re.sub(r'^www\.', '', д).split('/')[0].split('?')[0].strip()
    return д if re.match(r'^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$', д) else ''

db = EDB.EnrichDB()
чеко = {}
for и, с in db.cx.execute("SELECT inn, COALESCE(site_checko,'') FROM companies "
                          "WHERE COALESCE(site_checko,'')<>''"):
    чеко[str(и)] = домен(с)

цб = sqlite3.connect(P25, timeout=30)
поля = {r[1] for r in цб.execute('PRAGMA table_info(company)')}
ист_есть = 'istochnik_sayta' in поля
стат = Counter()
расхождения = []
подтв = []
for р in цб.execute(
        "SELECT inn, COALESCE(sayt,''), COALESCE(predpriyatie,'')" +
        (", COALESCE(istochnik_sayta,'')" if ист_есть else ", ''") +
        " FROM company"):
    и, наш, имя, ист = str(р[0]), домен(р[1]), str(р[2]), str(р[3])
    ч = чеко.get(и, '')
    от_чеко = 'чеко' in ист.lower()
    if not ч and not наш:
        стат['сайта нет ни у кого'] += 1
    elif ч and not наш:
        стат['есть у чеко, у нас пусто (лить)'] += 1
    elif наш and not ч:
        стат['есть у нас, чеко не знает'] += 1
    elif ч == наш:
        стат['ТОЛЬКО ЧЕКО (мой же залив, не подтверждение)' if от_чеко
             else 'СОВПАЛО — подтверждено двумя источниками'] += 1
        if not от_чеко:
            подтв.append((и, наш))
    else:
        стат['РАЗОШЛОСЬ — находка соседок под вопросом'] += 1
        расхождения.append({'inn': и, 'predpriyatie': имя[:60],
                            'u_nas': наш, 'u_cheko': ч,
                            'istochnik_nashego': ист or 'поиск 2-й сессии'})

for з in расхождения[:10]:
    print(f"   {з['inn']} у нас {з['u_nas'][:26]:26} ← чеко {з['u_cheko'][:26]}")
if расхождения:
    with io.open(ВЫХОД, 'w', encoding='utf-8-sig', newline='') as ф:
        п = csv.DictWriter(ф, fieldnames=list(расхождения[0]), delimiter=';')
        п.writeheader(); п.writerows(расхождения)
        ф.flush(); os.fsync(ф.fileno())

if ПРИМЕНИТЬ and подтв and 'istochnik_sayta' in поля:
    for и, д in подтв:
        цб.execute("UPDATE company SET istochnik_sayta=? WHERE inn=?",
                   ('подтверждён дважды: поиск + карточка чеко', и))
    цб.commit()
    стат['помечено как подтверждённое дважды'] = len(подтв)
цб.close()

print()
for к, v in sorted(стат.items()):
    print(f'{к:52} {v:5}')
print('файл расхождений:', os.path.basename(ВЫХОД) if расхождения else 'не нужен')
print('' if ПРИМЕНИТЬ else 'СУХОЙ ПРОГОН (пометки не проставлены)')
