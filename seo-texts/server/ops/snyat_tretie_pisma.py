# -*- coding: utf-8 -*-
"""Снять из расписания письма компаниям, у которых потолок адресов уже выбран.

Дыра: потолок «двух разных адресов на компанию» считает по send_log, то есть
по УЖЕ отправленным. Две копии, поставленные разными партиями до того, как
хоть одна ушла, обе проходят проверку законно — и компания получает третье
письмо. Владелец увидел два письма ТЗК «Имсб» с разницей в две минуты.
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
ПОТОЛОК = 2
ОКНО = 90
СЛЕД = r"C:\sender\_ops\snyato-tretih.jsonl"

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
порог = (datetime.now(timezone.utc) - timedelta(days=ОКНО)).isoformat()
# сколько РАЗНЫХ адресов компании уже получили письмо в окне
ушло = defaultdict(set)
for r in c.execute(
        "SELECT rc.inn, LOWER(rc.email) email FROM messages m "
        "  JOIN recipients rc ON rc.id=m.recipient_id "
        " WHERE m.status='sent' AND m.sent_at >= ?", (порог,)):
    if r["inn"]:
        ушло[str(r["inn"])].add(r["email"])
# что ещё стоит в расписании
стоят = c.execute(
    "SELECT m.id mid, m.scheduled_at, rc.inn, LOWER(rc.email) email, "
    "       rc.company_name, cr.id crid "
    "  FROM messages m JOIN recipients rc ON rc.id=m.recipient_id "
    "  LEFT JOIN confirm_reviews cr ON cr.message_id=m.id "
    " WHERE m.status IN ('scheduled','sending') ORDER BY m.scheduled_at").fetchall()
c.close()
print("в расписании: %d" % len(стоят))

# считаем нарастающим итогом: письма одной компании в очереди тоже занимают потолок
занято = {и: set(v) for и, v in ушло.items()}
снимать, оставить = [], Counter()
for r in стоят:
    инн = str(r["inn"] or "")
    if not инн:
        оставить["без ИНН"] += 1
        continue
    было = занято.setdefault(инн, set())
    if r["email"] in было:
        снимать.append((r, "этому адресу уже писали"))
        continue
    if len(было) >= ПОТОЛОК:
        снимать.append((r, "потолок компании: адресов уже %d" % len(было)))
        continue
    было.add(r["email"])
    оставить["оставляем"] += 1
наши = set()
for ф in (r"C:\sender\_ops\vtorye-adresa.jsonl",
          r"C:\sender\_ops\vtorye-adresa-2.jsonl"):
    try:
        for с2 in io.open(ф, encoding="utf-8"):
            d2 = json.loads(с2)
            if "review" in d2:
                наши.add(int(d2["review"]))
    except FileNotFoundError:
        pass
раскл = Counter()
for r, п in снимать:
    к = "партия вторых адресов" if (r["crid"] and int(r["crid"]) in наши) else "прочее"
    раскл["%s / %s" % (к, п.split(":")[0])] += 1
print("к снятию: %d, оставляем: %s" % (len(снимать), dict(оставить)))
for к, n in раскл.most_common():
    print("   %-52s %4d" % (к, n))
for r, п in снимать[:10]:
    print("   msg %-6s %-30s %-34s %s"
          % (r["mid"], str(r["email"])[:30], str(r["company_name"] or "")[:34], п))
if not КАТИТЬ or not снимать:
    raise SystemExit(0)

from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
итог = Counter()
поток = io.open(СЛЕД, "a", encoding="utf-8")
for r, п in снимать:
    try:
        n = 0
        if hasattr(store, "mark_skipped_if_not_terminal"):
            n = 1 if store.mark_skipped_if_not_terminal(
                int(r["mid"]), "потолок компании: " + п) else 0
        if n:
            итог["снято"] += 1
            поток.write(json.dumps({"msg": int(r["mid"]), "email": r["email"],
                                    "inn": r["inn"], "prichina": п},
                                   ensure_ascii=False) + "\n")
            поток.flush(); os.fsync(поток.fileno())
        else:
            итог["не снялось (уже терминальный)"] += 1
    except Exception as ex:                                      # noqa: BLE001
        итог["ошибка: " + str(ex)[:40]] += 1
поток.close()
print("")
for к, n in итог.most_common():
    print("   %-38s %4d" % (к, n))
