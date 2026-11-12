# -*- coding: utf-8 -*-
"""Когда уйдут письма кампании 22: окно отправки, расписание (scheduled_at) по барнаульскому времени, отправлено сегодня,
лимиты ящиков. Только чтение."""
import sqlite3, sys
from collections import Counter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
sys.path.insert(0, r"C:\sender")
from sender.config import Config
from sender.store import Store
from sender.auto_send import window_from
cfg = Config.load(r"C:\sender\sender.yaml"); st = Store(r"C:\sender\sender.db")
print("окно отправки:", window_from(st, cfg))
Б = ZoneInfo("Asia/Barnaul"); now = datetime.now(timezone.utc)
print("сейчас в Барнауле:", now.astimezone(Б).strftime("%d.%m %H:%M"))
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
def б(t):
    try: d = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    except ValueError: return "?"
    if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(Б).strftime("%d.%m %H:00")
р = c.execute("SELECT scheduled_at FROM messages WHERE campaign_id=22 AND status='scheduled'").fetchall()
print("в расписании:", len(р)); print("по часам (Барнаул):", sorted(Counter(б(x[0]) for x in р).items())[:30])
print("отправлено 22 по часам (Барнаул):", sorted(Counter(б(x[0]) for x in c.execute("SELECT sent_at FROM messages WHERE campaign_id=22 AND status='sent'")).items()))
кол = [r[1] for r in c.execute("PRAGMA table_info(mailboxes)")]
print("колонки mailboxes:", кол)
лим = next((к for к in кол if "daily" in к or "limit" in к), None)
if лим:
    ящ = c.execute("SELECT %s, COUNT(*) FROM mailboxes WHERE COALESCE(paused,0)=0 GROUP BY 1" % лим).fetchall() if "paused" in кол else c.execute("SELECT %s, COUNT(*) FROM mailboxes GROUP BY 1" % лим).fetchall()
    print("ящики по лимиту (лимит, сколько ящиков):", ящ)
print("ящики кампании 22 в расписании:", len({x[0] for x in c.execute("SELECT mailbox_id FROM messages WHERE campaign_id=22 AND status='scheduled'")}))
print("всего отправлено сегодня по всем кампаниям:", c.execute("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at>=?", (now.astimezone(Б).replace(hour=0, minute=0).astimezone(timezone.utc).isoformat()[:19],)).fetchone()[0])
print("в расписании прочих кампаний:", c.execute("SELECT campaign_id, COUNT(*) FROM messages WHERE status='scheduled' AND campaign_id!=22 GROUP BY 1").fetchall())
