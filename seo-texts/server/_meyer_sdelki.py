# -*- coding: utf-8 -*-
"""ИНН компаний «идёт сделка» из запретов панели (sender.db, scope=inn) — на дроп."""
import io, json, os, sqlite3
c = sqlite3.connect(r'file:C:\sender\sender.db?mode=ro', uri=True, timeout=60)
тт = [r[0] for r in c.execute("select name from sqlite_master where type='table' and name like '%suppress%'")]
o = {'таблицы': тт}
т = тт[0]
кол = [r[1] for r in c.execute('pragma table_info(%s)' % т)]
o['колонки'] = кол
o['по_scope_reason'] = c.execute('select scope, reason, source, count(*) from %s group by 1,2,3 order by 4 desc limit 30' % т).fetchall()
строки = c.execute("select * from %s where scope='inn'" % т).fetchall()
o['inn_строк'] = len(строки)
п = r'C:\sender\server\sdelki-inn.json'
with io.open(п, 'w', encoding='utf-8') as f:
    json.dump([dict(zip(кол, r)) for r in строки], f, ensure_ascii=False, default=str)
    f.flush(); os.fsync(f.fileno())
import shutil
shutil.copyfile(п, r'C:\seostat\drop\drop-storage\sdelki-inn.json')
c.close()
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, default=str, indent=0)[:3000])
