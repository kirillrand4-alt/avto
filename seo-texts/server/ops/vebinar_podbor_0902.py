# -*- coding: utf-8 -*-
"""Только чтение: боевой подбор ящика для писем кампании 12."""
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.suppression import Suppression  # noqa: E402
import sender.sender as S                   # noqa: E402
import sender.gates as G                    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
snd = S.Sender(cfg, store, Suppression(store), G.Gates(cfg, store))
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

ряды = list(s.execute("SELECT id, recipient_id, mailbox_id FROM messages"
                      " WHERE campaign_id=12 AND status='scheduled'"
                      " ORDER BY id LIMIT 40"))
camp = store.get_campaign(12)
c = Counter()
без = []
for р in ряды:
    rec = store.get_recipient(р["recipient_id"])
    msg = store.get_message(р["id"])
    try:
        mid = snd.pick_mailbox(rec, camp, message=msg)
    except Exception as ex:
        c["ОШИБКА %s" % str(ex)[:44]] += 1
        continue
    метка = "закреплён" if р["mailbox_id"] else "ротация"
    if mid:
        c["%s -> %s" % (метка, mid)] += 1
    else:
        c["%s -> ЯЩИК НЕ НАЙДЕН" % метка] += 1
        if len(без) < 3:
            без.append((р["id"], getattr(rec, "email", ""),
                        getattr(rec, "segment", ""), getattr(rec, "inn", "")))

print("=== ПОДБОР НА %d ПИСЬМАХ КАМПАНИИ 12 ===" % len(ряды))
for k, v in c.most_common():
    print("  %-56s %d" % (k[:56], v))
for i, e, sg, inn in без:
    print("     без ящика: msg#%s %s segment=%s инн=%s" % (i, e, sg, inn))

print("\n=== ЕСТЬ ЛИ СРЕДИ ПОДОБРАННЫХ КОМПРЕССОРНЫЕ ===")
мейер = {m["mailbox_id"] for m in cfg.get("mailboxes", [])
         if str(m.get("division")) == "meyer"}
чужие = [k for k in c if "-> " in k and k.split("-> ")[1] not in мейер
         and "НЕ НАЙДЕН" not in k]
print("  не-meyer ящиков в подборе: %d %s" % (len(чужие), чужие[:4]))

print("\n=== ОКНО ОТПРАВКИ СЕЙЧАС ===")
try:
    print("  внутри окна: %s" % snd._within_window(datetime.now().astimezone()))
except Exception as ex:
    print("  не проверить: %s" % str(ex)[:90])
print("  время панели: %s" % datetime.now().isoformat(timespec="seconds"))
