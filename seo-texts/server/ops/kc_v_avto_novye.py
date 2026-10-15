# -*- coding: utf-8 -*-
"""Новые письма КЦ (кампания 15, новый текст 15.10) — в автоотправку тем же путём,
что кнопка панели: слот в окне получателя + confirm_decide approved. Пропускаем
карточки с удержанием, заслоном адреса/компании и гейтом направлений, и письма
со старыми шаблонными фразами. Владелец 15.10: «направляй в очередь отправки».

    kc_v_avto_novye.py [--katit]
"""
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.auto_send import next_slot, recipient_tz_name, window_from  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.wiring import build_deps  # noqa: E402

КАТИТЬ = "--katit" in sys.argv
ШАБЛОН = re.compile(r"(?i)КП\s+с\s+цен|успеть\s+до\s+конца\s+года")
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = build_deps(cfg, store, dry_run=True).confirm
win = window_from(store, cfg)
now = datetime.now(timezone.utc)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
ряды = [dict(r) for r in c.execute(
    "SELECT id, inn, email, recipient_id, message_id, campaign_id, panel_json, body, subject FROM confirm_reviews "
    "WHERE campaign_id=15 AND status='pending' ORDER BY id")]
итог = Counter()
for r in ряды:
    if ШАБЛОН.search(r["body"] or "") or re.search(r"(?i)до\s+конца\s+года", r["subject"] or ""):
        итог["старый шаблон"] += 1
        continue
    п = json.loads(r["panel_json"] or "{}") or {}
    if (п.get("actions") or {}).get("confirm_hold"):
        итог["удержание: " + ",".join(sorted(str(f.get("code")) for f in п.get("stop_flags") or []))] += 1
        continue
    бл = cs._guard(inn=r["inn"], email=r["email"] or "")
    if бл:
        итог["заслон: " + re.sub(r"[\d:-]{6,}\S*", "", str(бл))[:40]] += 1
        continue
    if cs._division_blocked(r):
        итог["гейт направлений"] += 1
        continue
    rec = store.get_recipient(int(r["recipient_id"])) if r["recipient_id"] else None
    if rec is None or not r["message_id"]:
        итог["нет получателя/письма"] += 1
        continue
    if not КАТИТЬ:
        итог["перевели бы"] += 1
        continue
    store.reschedule_message(int(r["message_id"]), next_slot(win, recipient_tz_name(win, rec), now))
    ок = store.confirm_decide(r["id"], status="approved", decided_by="КЦ новый текст 15.10",
                              reason="bulk-to-auto: КЦ новый текст (владелец 15.10)")
    итог["в автоотправку" if ок else "решение не легло"] += 1
print(dict(итог))
print("=== КЦ В АВТО (НОВЫЕ): %s ===" % ("ПРИМЕНЕНО" if КАТИТЬ else "сухой прогон"))
