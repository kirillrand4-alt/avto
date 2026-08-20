# -*- coding: utf-8 -*-
r"""Что проба знала об адресах, которые потом отбились."""
import json, os, sqlite3

АДРЕСА = ['sales@premfire.ru','snab@taimyr-fish.ru','neapol.sklad@mail.ru',
          'hr@sibach.store','pastarellab@mail.ru','snab@konex.ru',
          'okna_sklad@alkona.net','office@dscavtostrada.com','shop@zavodsota.ru']
итог = {}
# найти таблицу пробы
for путь in (r'C:\sender\enrich.db', r'C:\sender\sender.db', r'C:\sender\obzvon-index.db'):
    if not os.path.exists(путь): continue
    con = sqlite3.connect('file:%s?mode=ro' % путь.replace('\\','/'), uri=True)
    con.row_factory = sqlite3.Row
    имена = [r[0] for r in con.execute(
        "select name from sqlite_master where type='table'")]
    итог.setdefault('где_проба', {})[os.path.basename(путь)] = [
        n for n in имена if 'probe' in n.lower() or 'proba' in n.lower()]
    con.close()

con = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True)
con.row_factory = sqlite3.Row
try:
    столбцы = [r[1] for r in con.execute('pragma table_info(addr_probe)')]
    итог['столбцы_addr_probe'] = столбцы
    q = ','.join('?' * len(АДРЕСА))
    итог['что_знала_проба'] = [dict(r) for r in con.execute(
        'select * from addr_probe where lower(email) in (%s)' % q,
        [a.lower() for a in АДРЕСА])]
    итог['всего_в_пробе'] = con.execute('select count(*) from addr_probe').fetchone()[0]
    итог['по_вердиктам'] = dict(con.execute(
        'select verdikt, count(*) from addr_probe group by verdikt').fetchall()) \
        if 'verdikt' in столбцы else 'нет столбца verdikt'
except Exception as e:
    итог['ошибка'] = '%s: %s' % (type(e).__name__, e)
con.close()
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3500])
