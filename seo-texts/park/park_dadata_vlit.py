# -*- coding: utf-8 -*-
"""461 предприятие парка стояло БЕЗ ИМЕНИ: машина доказана, а кому звонить — неизвестно
даже по названию. Берём имя, адрес, руководителя и статус из ЕГРЮЛ через dadata
(серверная задача), пишем в park.db.

Руководитель — это круг 4 (не техконтакт), но для 461 предприятия без единого контакта
это лучше, чем пусто: с него начинают, чтобы выйти на главного инженера.
Статус ЕГРЮЛ важен отдельно: ликвидированному звонить незачем.
"""
import json, os, subprocess, sqlite3, sys, time

D = os.path.dirname(os.path.abspath(__file__))
SERV = '/home/user/avto/seo-texts/server'
p = sqlite3.connect(os.path.join(D, 'park.db')); cur = p.cursor()
cur.executescript("""
CREATE TABLE IF NOT EXISTS egrul(
  inn TEXT PRIMARY KEY, imya TEXT, adres TEXT, rukovoditel TEXT, dolzhnost_ruk TEXT,
  status TEXT, okved TEXT, istochnik TEXT, ts TEXT);
""")
spisok = json.load(open(os.path.join(D, 'park_bez_imeni.json'), encoding='utf-8'))
est = {r[0] for r in cur.execute('select inn from egrul')}
ochered = [c for c in spisok if c['inn'] not in est]
print('без имени: %d | уже разобрано: %d | к разбору: %d' % (len(spisok), len(est), len(ochered)))
vsego = 0
for i in range(0, len(ochered), 200):
    pach = ochered[i:i + 200]
    zad = json.dumps({'companies': pach}, ensure_ascii=False)
    try:
        out = subprocess.run([sys.executable, 'run_on_server.py', 'dadata', zad],
                             cwd=SERV, capture_output=True, text=True, timeout=900).stdout
        d = json.loads(out[out.index('{'):])
        res = d['data']['results']
    except Exception as e:
        print('пачка %d СБОЙ %r' % (i, e)); continue
    for r in res:
        cur.execute('insert or replace into egrul values (?,?,?,?,?,?,?,?,datetime("now"))',
                    (r.get('inn'), r.get('full_name') or r.get('name') or '',
                     r.get('address') or '', r.get('mgmt_name') or '',
                     r.get('mgmt_post') or '', r.get('status') or '',
                     r.get('okved') or '', 'dadata/ЕГРЮЛ'))
        vsego += 1
    p.commit()
    print('пачка %d-%d: получено %d' % (i, i + len(pach), len(res)), flush=True)
print('\nвлито записей ЕГРЮЛ:', vsego)
print('  с именем:', cur.execute("select count(*) from egrul where imya<>''").fetchone()[0])
print('  с руководителем:', cur.execute("select count(*) from egrul where rukovoditel<>''").fetchone()[0])
import collections
print('  статусы:', dict(collections.Counter(
    r[0] for r in cur.execute('select status from egrul')).most_common(6)))
p.close()
