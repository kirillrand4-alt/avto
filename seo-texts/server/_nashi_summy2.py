# -*- coding: utf-8 -*-
import json, sqlite3
c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=30)
o = {
 'всего': c.execute('select count(*) from signals').fetchone()[0],
 'с_суммой': c.execute("select count(*) from signals where coalesce(sum,'')<>''").fetchone()[0],
 'свежих_всего': c.execute("select count(*) from signals where substr(updated_at,1,10)>='2026-09-16'").fetchone()[0],
 'свежих_с_суммой': c.execute("select count(*) from signals where coalesce(sum,'')<>'' and substr(updated_at,1,10)>='2026-09-16'").fetchone()[0],
}
c.close()
o['доля_всего'] = round(100.0*o['с_суммой']/max(o['всего'],1), 1)
o['доля_свежих'] = round(100.0*o['свежих_с_суммой']/max(o['свежих_всего'],1), 1)
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
