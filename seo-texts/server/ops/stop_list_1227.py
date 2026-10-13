# -*- coding: utf-8 -*-
"""Откуда 1227 записей стоп-листа «bounce_hard» за сегодня: время, источник, были ли раньше."""
import sqlite3
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
кол = [р[1] for р in c.execute("PRAGMA table_info(suppression)")]
print("колонки suppression: %s" % кол)
строки = [dict(р) for р in c.execute("SELECT * FROM suppression WHERE created_at >= date('now') AND reason='bounce_hard'")]
print("за сегодня: %d" % len(строки))
print("по часу: %s" % dict(sorted(Counter(str(р["created_at"])[:13] for р in строки).items())))
for к in кол:
    if к in ("source", "note", "detail", "added_by", "meta", "comment"):
        print("по %s: %s" % (к, dict(Counter(str(р.get(к))[:50] for р in строки).most_common(5))))
вер = {р[0].lower(): (р[1], р[2]) for р in c.execute("SELECT email, verdict, coalesce(source,'') FROM addr_probe")}
print("их вердикт пробы: %s" % dict(Counter((вер.get(str(р["value"]).lower()) or ("нет", ""))[0] for р in строки).most_common()))
print("источник вердикта: %s" % dict(Counter((вер.get(str(р["value"]).lower()) or ("", "нет"))[1][:20] for р in строки).most_common(5)))
ушло = {р[0].lower() for р in c.execute("SELECT DISTINCT r.email FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status IN ('sent','bounced')")}
print("из них нам когда-либо слали письмо: %d" % sum(1 for р in строки if str(р["value"]).lower() in ушло))
print("примеры: %s" % [str(р["value"]) for р in строки[:5]])
print("=== СТОП-ЛИСТ 1227 ===")
