# -*- coding: utf-8 -*-
"""Только чтение: отбилось ли письмо 6929 на cmg-info@cryo-gas.ru."""
import json
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
for р in c.execute("SELECT id, event_type, event_ts, message_id,"
                   " substr(IFNULL(detail_json,''),1,300) d FROM events"
                   " WHERE recipient_id=17738 ORDER BY id"):
    d = р["d"]
    try:
        j = json.loads(р["d"] + "}" * 0) if р["d"].strip().startswith("{") else {}
    except Exception:                                            # noqa: BLE001
        j = {}
    print("  ev=%s %-10s %s msg=%s" % (р["id"], р["event_type"],
                                       str(р["event_ts"])[:19], р["message_id"]))
    print("      %s" % d[:220].replace("\n", " "))
