# -*- coding: utf-8 -*-
"""Куда легли письма, переведённые в автоотправку, и когда они уедут.

Владелец: «ты же перекинул 140 вроде», а в кампании 11 ждут 62. Перевод шёл
по вердикту рецензента, а вердикты есть у обеих кампаний - значит часть
легла в компрессорную очередь. Заодно считаем, когда очередь разойдётся:
это упирается в дневные лимиты ящиков, а не в размер очереди.
"""
import io
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

Ж = r"C:\sender\_ops\godnye-v-avtootpravku.jsonl"
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

строки = []
for s in io.open(Ж, encoding="utf-8", errors="replace"):
    try:
        строки.append(json.loads(s))
    except Exception:                                            # noqa: BLE001
        pass
последние = строки[-141:]
счёт = Counter()
for z in последние:
    rid = z.get("id")
    if rid is None:
        continue
    with store._lock:
        r = store._conn.execute(
            "SELECT c.campaign_id, c.status, COALESCE(m.status,'') "
            "FROM confirm_reviews c LEFT JOIN messages m ON m.id=c.message_id "
            "WHERE c.id=?", (int(rid),)).fetchone()
    счёт[f"кампания {r[0]} / {r[1]} / письмо {r[2] or '—'}" if r
         else "строки нет"] += 1
print(f"последний перевод в автоотправку: {len(последние)} писем")
for k, n in счёт.most_common():
    print(f"  {n:>4}  {k}")

print("\n== сколько ждёт отправки сейчас ==")
with store._lock:
    ряды = store._conn.execute(
        "SELECT c.campaign_id, COUNT(*) FROM messages m "
        "JOIN confirm_reviews c ON c.message_id=m.id "
        "WHERE c.status='approved' AND m.status='scheduled' "
        "GROUP BY c.campaign_id ORDER BY 2 DESC").fetchall()
    ушло = dict(store._conn.execute(
        "SELECT c.campaign_id, COUNT(*) FROM messages m "
        "JOIN confirm_reviews c ON c.message_id=m.id "
        "WHERE m.status='sent' AND date(m.sent_at)=date('now') "
        "GROUP BY c.campaign_id").fetchall())
всего_ждут = 0
for камп, n in ряды:
    всего_ждут += n
    print(f"  кампания {камп}: ждут {n}, ушло сегодня {ушло.get(камп, 0)}")

print("\n== когда разойдётся: лимиты ящиков ==")
per = ((store.get_setting("send_limits") or {}) or {}).get("per_mailbox") or {}
дневной = {"kc": 0, "meyer": 0}
for mb in cfg.mailboxes():
    d = "meyer" if "meyer" in str(getattr(mb, "division", "")).lower() else "kc"
    лимит = per.get(mb.mailbox_id)
    if лимит is None:
        лимит = 0
    дневной[d] += int(лимит or 0)
print(f"  суммарный дневной потолок: КЦ {дневной['kc']}, "
      f"Meyer {дневной['meyer']}")
окно = store.get_setting("sending_window") or {}
print(f"  окно: {окно.get('start')}-{окно.get('end')} "
      f"({'по времени получателя' if окно.get('by_recipient_tz') else 'по МСК'})"
      f", дни {окно.get('days')}")
