# -*- coding: utf-8 -*-
r"""Скорость отправки против скорости пробы — кто кого обгоняет."""
import json, sqlite3
c = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True)
c.row_factory = sqlite3.Row
итог = {}
итог['отправки_по_часам'] = [dict(r) for r in c.execute(
    "select substr(ts,1,13) час, count(*) n from send_log "
    "where ts >= datetime('now','-30 hour') group by 1 order by 1 desc limit 12")]
итог['проба_по_часам'] = [dict(r) for r in c.execute(
    "select substr(ts,1,13) час, count(*) n from addr_probe "
    "where coalesce(source,'')='проба' and ts >= datetime('now','-30 hour') "
    'group by 1 order by 1 desc limit 12')]
итог['всего_проба'] = c.execute(
    "select count(*) from addr_probe where coalesce(source,'')='проба'").fetchone()[0]
итог['первая_и_последняя_проба'] = dict(c.execute(
    "select min(ts) первая, max(ts) последняя from addr_probe "
    "where coalesce(source,'')='проба'").fetchone())
итог['очередь_подтверждений'] = dict(c.execute(
    "select status, count(*) n from confirm_reviews group by status").fetchall())
# сколько в очереди СЕЙЧАС без вердикта
без = c.execute("""select count(*) from confirm_reviews cr
    where cr.status in ('pending','new','queued')
      and not exists (select 1 from addr_probe p
                      where lower(p.email)=lower(cr.email))""").fetchone()[0]
итог['в_очереди_без_вердикта'] = без
c.close()
print(json.dumps(итог, ensure_ascii=False, indent=1))
