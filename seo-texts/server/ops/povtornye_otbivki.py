# -*- coding: utf-8 -*-
"""Почему один адрес отбился сегодня дважды: два письма или два уведомления."""
import json
import sqlite3
from collections import defaultdict
БАЗА = r"C:\sender\sender.db"
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
по_адресу = defaultdict(list)
for r in c.execute(
        "SELECT e.id, e.event_ts, e.dedup_key, e.mailbox_id, e.detail_json, "
        "       r.email, r.inn, r.id AS rid FROM events e "
        "  LEFT JOIN recipients r ON r.id=e.recipient_id "
        " WHERE e.event_type='bounce' AND e.event_ts LIKE '2026-08-28%'"):
    if r["email"]:
        по_адресу[str(r["email"]).lower()].append(dict(r))
повторы = {а: v for а, v in по_адресу.items() if len(v) > 1}
print("адресов с двумя и более отбивками сегодня: %d" % len(повторы))
for адрес, список in sorted(повторы.items()):
    inn = список[0]["inn"]
    писем = c.execute(
        "SELECT COUNT(*) FROM messages m JOIN recipients r ON r.id=m.recipient_id "
        " WHERE LOWER(r.email)=? AND m.sent_at IS NOT NULL", (адрес,)).fetchone()[0]
    журнал = c.execute("SELECT COUNT(*) FROM send_log WHERE LOWER(email)=?",
                       (адрес,)).fetchone()[0]
    print("\n%s  (ИНН %s) — писем отправлено: %d, в журнале отправок: %d"
          % (адрес, inn, писем, журнал))
    for э in список:
        try:
            d = json.loads(э["detail_json"] or "{}")
        except Exception:
            d = {}
        dsn = d.get("dsn") if isinstance(d.get("dsn"), dict) else {}
        h = d.get("headers") or {}
        print("   ev=%-7s %s ключ=%-30s ящик=%s"
              % (э["id"], str(э["event_ts"])[11:19], str(э["dedup_key"])[:30],
                 str(э["mailbox_id"])[:34]))
        print("      Message-ID: %s" % str(h.get("Message-ID") or "—")[:60])
        print("      вердикт=%s  %s" % (dsn.get("verdict") or "—",
                                        str(dsn.get("diagnostic")
                                            or d.get("snippet") or "")
                                        .replace("\n", " ")[:110]))
print("\n=== кривые адреса среди сегодняшних отбивок ===")
for r in c.execute(
        "SELECT DISTINCT LOWER(r.email) AS e FROM events ev "
        "  JOIN recipients r ON r.id=ev.recipient_id "
        " WHERE ev.event_type='bounce' AND ev.event_ts LIKE '2026-08-28%'"):
    ло = str(r["e"]).split("@")[0]
    if ло in ("nfo", "yh", "nfo1", "mail1") or len(ло) <= 3:
        print("   %s" % r["e"])
c.close()
