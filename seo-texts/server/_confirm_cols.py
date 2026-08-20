# -*- coding: utf-8 -*-
import json, sqlite3
c = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True)
d = {'confirm_reviews': [r[1] for r in c.execute('pragma table_info(confirm_reviews)')]}
d['копий_автоответа'] = dict(c.execute(
    "select status, count(*) from confirm_reviews "
    "where dedup_key like 'avtootvet:%' group by status").fetchall())
d['примеры'] = [dict(zip(('id','email','status','dedup_key','recipient_id'), r))
                for r in c.execute(
    "select id, email, status, dedup_key, recipient_id from confirm_reviews "
    "where dedup_key like 'avtootvet:%' limit 5")]
c.close()
print(json.dumps(d, ensure_ascii=False, indent=1)[:1800])
