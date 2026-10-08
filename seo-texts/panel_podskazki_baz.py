# -*- coding: utf-8 -*-
"""Подсказки у меток баз – словами владельца (08.10): «база 2 = ЛПР с остальными телефонами,
файл 3 – номера без ролей, файл 4 – Common Crawl, файл 6 – поиск агентами по узкому списку
отраслей». У компании метка и подсказка идут парами через « | » (bazy / bazy_opisanie) –
подсказки пересобираются по меткам, порядок меток не меняется."""
import os, shutil, sqlite3, time
KAT = r'C:\centro2\data\meyer_baza1.db'
PODSK = {'База 1': 'ЛПР с мобильными и добавочными', 'База 2': 'ЛПР с остальными телефонами',
         'База 3': 'номера без ролей', 'База 4': 'Common Crawl',
         'База 6': 'поиск агентами по узкому списку отраслей'}
B = os.path.join(r'C:\centro2\_bekap', time.strftime('podskazki-%Y%m%d-%H%M%S'))
os.makedirs(B, exist_ok=True)
k = sqlite3.connect(KAT)
d = sqlite3.connect(os.path.join(B, 'meyer_baza1.db'))
k.backup(d)
d.close()
n = 0
neizv = set()
for inn, bazy, op in k.execute('select inn, bazy, bazy_opisanie from company').fetchall():
    metki = [b.strip() for b in (bazy or '').split('|') if b.strip()]
    novo = ' | '.join(PODSK.get(m, '') for m in metki)
    neizv |= {m for m in metki if m not in PODSK}
    if novo != (op or ''):
        k.execute('update company set bazy_opisanie=? where inn=?', (novo, inn))
        n += 1
k.commit()
print('подсказок обновлено: %d; неизвестные метки: %s' % (n, sorted(neizv) or 'нет'))
for r in k.execute("select bazy, bazy_opisanie, count(*) from company group by 1, 2 order by 3 desc"):
    print('   %-24s | %-75s | %d' % r)
