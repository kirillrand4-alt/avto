# -*- coding: utf-8 -*-
"""Фаза 3, влив: вердикты линз (AK-linzy-itog.jsonl с дропа) -> predpriyatiya.klass/uverennost/tehprocess/tip_mashin.
Предприятиям с прямым фактом класс «доказано» ставится независимо от линз. Идемпотентно."""
import os, sys, json, sqlite3, urllib.request, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite')
dest = os.path.join(AK, 'AK-linzy-itog.jsonl')
req = urllib.request.Request(os.environ['DROP_URL'].rstrip('/') + '/AK-linzy-itog.jsonl', headers={'X-Drop-Token': os.environ['DROP_TOKEN']})
with urllib.request.urlopen(req, timeout=600) as r, open(dest, 'wb') as f:
    f.write(r.read())
c = sqlite3.connect(DB, timeout=120)
n = 0
for l in open(dest, encoding='utf-8'):
    try: d = json.loads(l)
    except Exception: continue
    if 'kontrol' in d or not str(d.get('inn', '')).isdigit(): continue
    c.execute("update predpriyatiya set klass=?, uverennost=?, tehprocess=?, tip_mashin=? where inn=? and inn not in (select inn from fakty where sila>=3)",
              (d['klass'], d.get('uverennost'), (d.get('tehprocess') or '')[:400], ','.join(d.get('tip_mashin') or []), d['inn'])); n += c.total_changes and 1
c.execute("update predpriyatiya set klass='доказано' where inn in (select inn from fakty where sila>=3)")
c.execute("update predpriyatiya set klass='доказано (слабо)' where klass is null and inn in (select inn from fakty)")
c.commit()
print('вердиктов применено', n, '| классы:', c.execute('select klass, count(*) from predpriyatiya group by 1 order by 2 desc').fetchall())
c.close()
