# -*- coding: utf-8 -*-
"""mailbox_state по ящикам: sent_today, day_key, ramp_day, last_sent_at, пауза; гейты (глобальный и ящика). Только чтение."""
import sqlite3, sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config
from sender.store import Store
from sender.gates import Gates
cfg = Config.load(r"C:\sender\sender.yaml"); st = Store(r"C:\sender\sender.db"); g = Gates(cfg, st)
print("глобальный гейт:", g.check_global())
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
кол = [r[1] for r in c.execute("PRAGMA table_info(mailbox_state)")]
print(кол)
for р in c.execute("SELECT * FROM mailbox_state ORDER BY mailbox_id"):
    д = dict(zip(кол, р))
    if "kompressor" in д["mailbox_id"] or "compressor" in д["mailbox_id"]:
        гм = g.check_mailbox(д["mailbox_id"])
        print("%-44s %s | гейт: %s" % (д["mailbox_id"], {k: д[k] for k in кол if k not in ("mailbox_id",)}, "ЗАКРЫТ " + str(getattr(гм, "reason", "")) if гм.tripped else "ок"))
