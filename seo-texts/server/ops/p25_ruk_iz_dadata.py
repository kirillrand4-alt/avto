# -*- coding: utf-8 -*-
"""Руководители: выкинуть улов чеко целиком и взять их из DaData.

ЗАМЕР ЧЕСТНЫЙ: из 83 «руководителей», снятых разбором чеко,人 не оказалось ни
одного. 81 — прямая навигация страницы («Учредитель Связи Лицензии»), а два
«похожих» при взгляде глазами тоже не люди: «Директор Имеется» и «Директор
Шкарупа Андрей» (слово должности приклеено к имени). Канал дал НОЛЬ, и половину
чинить нечего — надо брать оттуда, где данные чистые.

DaData отдала `director` и `director_post` по ВСЕМ 491 из ЕГРЮЛ. Это
первоисточник, а не разбор вёрстки, и ФИО там в готовом виде.

Руководитель — 4-й круг: по ТЗ его берут, только если выше никого не нашли, и в
главную меру он не идёт. Роль ставлю явно, чтобы это было видно на карточке.

Запуск: python p25_ruk_iz_dadata.py [--apply]
"""
import json
import re
import sqlite3
import sys
import time
from collections import Counter

P25 = r'C:\seostat\data\p25.db'
ПРИМЕНИТЬ = '--apply' in sys.argv
sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

НЕ_ЧЕЛОВЕК = re.compile(
    r'учредител|филиал|лиценз|реквизит|контакт|связи|отчётност|отчетност|'
    r'имеется|подразделен|сведени|директор\s+имеется', re.I)

цб = sqlite3.connect(P25, timeout=30)
наши = {str(r[0]) for r in цб.execute('SELECT inn FROM company')}
поля_p = [r[1] for r in цб.execute('PRAGMA table_info(person)')]

# 1) выкинуть весь улов чеко по руководителям
плохие = [r[0] for r in цб.execute(
    "SELECT rowid FROM person WHERE role LIKE '%4 круг%'")]
print('руководителей от чеко к удалению:', len(плохие))

# 2) взять из DaData
db = EDB.EnrichDB()
хорошие = []
с = Counter()
for инн, фио, долж in db.cx.execute(
        "SELECT inn, COALESCE(director,''), COALESCE(director_post,'') "
        "FROM requisites WHERE COALESCE(director,'')<>''"):
    и = str(инн)
    if и not in наши:
        continue
    ф = ' '.join(str(фио).split())
    с['есть в requisites'] += 1
    if len(ф.split()) < 2 or НЕ_ЧЕЛОВЕК.search(ф):
        с['  не похоже на человека — пропуск'] += 1
        continue
    с['  ГОДЕН'] += 1
    хорошие.append((и, ф, str(долж or 'руководитель')))
print(json.dumps(dict(с.most_common()), ensure_ascii=False, indent=1))
for и, ф, д in хорошие[:8]:
    print(f'   {и} {ф[:34]:34} {д[:40]}')

if not ПРИМЕНИТЬ:
    print('\nСУХОЙ ПРОГОН, ничего не изменено')
    цб.close()
    raise SystemExit(0)

до = цб.total_changes
for i in range(0, len(плохие), 400):
    к = плохие[i:i + 400]
    цб.execute(f"DELETE FROM person WHERE rowid IN ({','.join('?' * len(к))})", к)
сегодня = time.strftime('%Y-%m-%d')
for и, ф, д in хорошие:
    зн = {'inn': и, 'person': ф, 'position': д,
          'role': '4 круг: руководство (ЕГРЮЛ)',
          'source': 'ЕГРЮЛ через DaData findById/party', 'source_url': '',
          'data_podtverzhdeniya': сегодня,
          'chem_podtverzhdena': 'единоличный исполнительный орган по ЕГРЮЛ',
          'is_tech': 0}
    имена = [к for к in поля_p if к in зн]
    цб.execute(f"INSERT OR IGNORE INTO person ({','.join(имена)}) "
               f"VALUES ({','.join('?' * len(имена))})", [зн[к] for к in имена])
цб.commit()
всего = цб.execute('SELECT COUNT(*) FROM person').fetchone()[0]
рук = цб.execute("SELECT COUNT(*) FROM person WHERE role LIKE '%4 круг%'").fetchone()[0]
тех = цб.execute("SELECT COUNT(*) FROM person WHERE COALESCE(is_tech,0)=1").fetchone()[0]
цб.close()
print(f'\nлюдей всего: {всего} | руководителей: {рук} | технических: {тех}')
