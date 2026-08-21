# -*- coding: utf-8 -*-
r"""Завёлся ли лид на нашем же письме к самим себе (ИНН 2124009521)."""
import json
import sqlite3

s = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True, timeout=60)
s.row_factory = sqlite3.Row
d = {}
d['лиды_по_адресу'] = [dict(r) for r in s.execute(
    "select id, email, company_name, coalesce(inn,'') inn, status, "
    "coalesce(created_at,'') created from leads "
    "where lower(coalesce(email,'')) like '%kompressor-%' "
    "or lower(coalesce(email,'')) like '%sort-systems%'")]
d['лид_по_recipient'] = [dict(r) for r in s.execute(
    'select id, email, company_name, status from leads where recipient_id=?',
    (1227,))]
d['события_1227'] = [dict(r) for r in s.execute(
    "select event_type, event_ts, substr(coalesce(detail_json,''),1,180) dj "
    'from events where recipient_id=? order by id', (1227,))]
s.close()
print(json.dumps(d, ensure_ascii=False, indent=1)[:2600])
