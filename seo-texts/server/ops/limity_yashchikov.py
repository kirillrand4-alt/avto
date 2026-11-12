# -*- coding: utf-8 -*-
"""Дневные лимиты ящиков (без паролей) и сколько ящиков у кампаний в расписании. Только чтение."""
import sqlite3, sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.config import Config
cfg = Config.load(r"C:\sender\sender.yaml")
ящ = cfg.get("mailboxes", []) or []
лим = {}
for м in ящ:
    if isinstance(м, dict):
        лим[str(м.get("id") or м.get("email") or м.get("address"))] = м.get("daily_limit") or м.get("limit_per_day") or м.get("daily_cap")
print("ящиков в конфиге:", len(ящ), "| ключи первого:", sorted(k for k in (ящ[0] if ящ and isinstance(ящ[0], dict) else {}) if "pass" not in k.lower() and "secret" not in k.lower()))
print("лимиты:", Counter(лим.values()).most_common())
st = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
for t in ("panel_settings", "settings"):
    try: print(t, [r for r in st.execute("SELECT key, substr(value,1,200) FROM %s WHERE key LIKE '%%limit%%' OR key LIKE '%%cap%%' OR key LIKE '%%ceiling%%' OR key LIKE '%%потол%%'" % t)])
    except Exception as ex: print(t, ex)
к22 = {x[0] for x in st.execute("SELECT DISTINCT mailbox_id FROM messages WHERE campaign_id=22 AND status='scheduled'")}
for камп in (13, 18, 20, 21):
    д = {x[0] for x in st.execute("SELECT DISTINCT mailbox_id FROM messages WHERE campaign_id=? AND status='scheduled'", (камп,))}
    print("кампания %d: ящиков %d, общих с 22: %d" % (камп, len(д), len(д & к22)))
print("лимиты ящиков 22:", Counter(лим.get(str(x)) for x in к22).most_common())
import json
д = json.loads(st.execute("SELECT value FROM panel_settings WHERE key='send_limits'").fetchone()[0])
pm = д.get("per_mailbox") or {}
print("send_limits all:", д.get("all"), "| ключи:", [k for k in д if k != "per_mailbox"])
print("лимиты ящиков 22 из панели:", Counter(pm.get(x) for x in к22).most_common(), "| сумма:", sum(pm.get(x) or 0 for x in к22))
print("в расписании у ящиков 22: камп 21 =", st.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=21 AND status='scheduled'").fetchone()[0],
      "камп 20 =", st.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=20 AND status='scheduled'").fetchone()[0])
print("кампании 20/21:", st.execute("SELECT id, name, status FROM campaigns WHERE id IN (20,21,22)").fetchall())
