# -*- coding: utf-8 -*-
"""Сами баунсы: последние события отказа с адресом, кампанией и текстом причины."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
c.row_factory = sqlite3.Row
итог = {}
try:
    итог['типы_событий'] = [dict(r) for r in c.execute(
        "select event_type, count(*) skolko, max(event_ts) posledniy "
        "from delivery_events group by event_type order by skolko desc")]
except Exception as e:  # noqa: BLE001
    итог['ошибка_типов'] = str(e)[:100]
try:
    итог['последние_отказы'] = [dict(r) for r in c.execute(
        "select de.event_ts, de.event_type, de.provider, de.campaign_id, "
        "coalesce(r.email,'') email, coalesce(r.inn,'') inn, "
        "substr(coalesce(de.detail_json,''),1,400) detail "
        "from delivery_events de left join recipients r on r.id=de.recipient_id "
        "where de.event_type not in ('sent','delivered','open','click') "
        "order by de.event_ts desc limit 10")]
except Exception as e:  # noqa: BLE001
    итог['ошибка_отказов'] = str(e)[:200]
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3500])
c.close()
