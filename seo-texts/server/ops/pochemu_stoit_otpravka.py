# -*- coding: utf-8 -*-
"""Почему стоит отправка: время/окно, последние отправки, письма в расписании по ящикам — есть ли ящик в конфиге и не
на паузе ли; свежие ошибки автоотправки в логе. Только чтение."""
import io, os, re, sqlite3, sys, time
from collections import Counter
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.config import Config
from sender.store import Store
from sender.auto_send import window_from
cfg = Config.load(r"C:\sender\sender.yaml"); st = Store(r"C:\sender\sender.db")
print("сейчас UTC:", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "| окно:", window_from(st, cfg))
ящ = {m.mailbox_id: m for m in cfg.mailboxes()}
print("ящиков в конфиге:", len(ящ), Counter(m.division for m in ящ.values()))
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
print("последняя отправка:", c.execute("SELECT MAX(sent_at) FROM messages WHERE status='sent'").fetchone()[0],
      "| за 60 мин:", c.execute("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at>=datetime('now','-60 minutes')").fetchone()[0])
пауз = set()
try:
    for (mb,) in c.execute("SELECT mailbox_id FROM mailbox_state WHERE paused=1"): пауз.add(mb)
except Exception as ex: print("mailbox_state:", ex)
сч = Counter()
for mb, n in c.execute("SELECT mailbox_id, COUNT(*) FROM messages WHERE status='scheduled' GROUP BY 1"):
    сч["нет в конфиге" if mb not in ящ else ("на паузе" if mb in пауз else "ящик ок")] += n
print("в расписании по состоянию ящика:", dict(сч))
print("в расписании, ящика нет в конфиге:", c.execute("SELECT mailbox_id, campaign_id, COUNT(*) FROM messages WHERE status='scheduled' GROUP BY 1,2").fetchall() and
      [(mb, к, n) for mb, к, n in c.execute("SELECT mailbox_id, campaign_id, COUNT(*) FROM messages WHERE status='scheduled' GROUP BY 1,2") if mb not in ящ][:20])
print("на паузе:", sorted(пауз))
print("ошибки за 2 часа:", c.execute("SELECT substr(last_error,1,80), COUNT(*) FROM messages WHERE updated_at>=datetime('now','-120 minutes') AND COALESCE(last_error,'')<>'' GROUP BY 1 ORDER BY 2 DESC LIMIT 8").fetchall())
п = r"C:\sender\_ops\panel_err.log"
р = os.path.getsize(п)
with io.open(п, "rb") as f: f.seek(max(0, р - 300000)); х = f.read().decode("utf-8", "replace").splitlines()
print("лог ошибок изменён:", time.strftime("%H:%M", time.localtime(os.path.getmtime(п))))
print("\n".join(x[:200] for x in [x for x in х if re.search(r"Error|auto_send|Exception", x)][-10:]))
