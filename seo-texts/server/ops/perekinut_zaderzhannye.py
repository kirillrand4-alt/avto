# -*- coding: utf-8 -*-
"""Перекинуть в автоотправку письма, которые держат нестрогие стоп-флаги.

Владелец 28.08: «перекидывай».

Берём карточки, у которых флаги ТОЛЬКО из мягкого набора:
  · out_of_base_allowed — «ИНН вне базы обзвона», и сам флаг говорит
    «отправка разрешена»: он информационный, а держит как блокирующий;
  · recent_contact — метка старого правила «писали компании <90 дней».
    Ровно то, что мы сегодня переделали: второму адресу писать можно.
site_mismatch НЕ трогаем: там сайт не этой компании, это про данные.

Каждую карточку всё равно прогоняем через живой заслон confirm._guard —
если он режет по новым правилам, письмо остаётся.
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
sys.path.insert(1, r"C:\sender\sender")
КАТИТЬ = "--katit" in sys.argv
МЯГКИЕ = {"out_of_base_allowed", "recent_contact"}
СЛЕД = r"C:\sender\_ops\perekinuto-zaderzhannyh.jsonl"

партии = {}
for ф in (r"C:\sender\_ops\vtorye-adresa.jsonl", r"C:\sender\_ops\vtorye-adresa-2.jsonl"):
    try:
        for с in io.open(ф, encoding="utf-8"):
            d = json.loads(с)
            if "review" in d:
                партии[int(d["review"])] = 1
    except FileNotFoundError:
        pass
вердикт = {}
for ф in (r"C:\sender\_ops\sud-vtoryh.jsonl", r"C:\sender\_ops\sud-vtoryh-2.jsonl"):
    try:
        for с in io.open(ф, encoding="utf-8"):
            d = json.loads(с)
            вердикт[int(d["id"])] = str(d.get("verdikt") or "").replace(
                "o", "о").replace("p", "р")
    except FileNotFoundError:
        pass

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
зн = ",".join("?" * len(партии))
строки = c.execute(
    "SELECT id, inn, email, recipient_id, message_id, panel_json "
    "  FROM confirm_reviews WHERE id IN (%s) AND status='pending' "
    " ORDER BY id" % зн, list(партии)).fetchall()
c.close()
print("в pending: %d" % len(строки))

from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.wiring import build_deps                              # noqa: E402
from sender.auto_send import next_slot, recipient_tz_name, window_from  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = build_deps(cfg, store, dry_run=True).confirm
win = window_from(store, cfg)
now = datetime.now(timezone.utc)

сделано = set()
if os.path.exists(СЛЕД):
    for с in io.open(СЛЕД, encoding="utf-8", errors="replace"):
        try:
            сделано.add(int(json.loads(с)["review"]))
        except Exception:                                        # noqa: BLE001
            pass
итог = Counter()
поток = io.open(СЛЕД, "a", encoding="utf-8") if КАТИТЬ else None
for r in строки:
    rid_ = int(r["id"])
    if rid_ in сделано:
        итог["уже перекинуто"] += 1
        continue
    в = вердикт.get(rid_, "не судили")
    if в == "не отправлять":
        итог["судья: не отправлять"] += 1
        continue
    try:
        п = json.loads(r["panel_json"] or "{}") or {}
    except Exception:                                            # noqa: BLE001
        п = {}
    коды = {(f.get("code") if isinstance(f, dict) else str(f))
            for f in (п.get("stop_flags") or [])}
    жёсткие = коды - МЯГКИЕ
    if жёсткие:
        итог["жёсткий флаг: " + "+".join(sorted(жёсткие))[:34]] += 1
        continue
    блок = None
    try:
        блок = cs._guard(inn=r["inn"], email=r["email"] or "")
    except Exception:                                            # noqa: BLE001
        блок = None
    if блок:
        итог["живой заслон: " + str(блок)[:34]] += 1
        continue
    try:
        дб = cs._division_blocked(dict(r))
    except Exception:                                            # noqa: BLE001
        дб = None
    if дб:
        итог["гейт направлений"] += 1
        continue
    rec = store.get_recipient(int(r["recipient_id"])) if r["recipient_id"] else None
    if rec is None or r["message_id"] is None:
        итог["нет получателя/письма"] += 1
        continue
    if not КАТИТЬ:
        итог["перекинули бы (%s)" % в] += 1
        continue
    try:
        слот = next_slot(win, recipient_tz_name(win, rec), now)
        store.reschedule_message(int(r["message_id"]), слот)
        ок = store.confirm_decide(
            rid_, status="approved", decided_by="снятие мягких флагов 28.08",
            reason="bulk-to-auto: копия на второй адрес (мягкий флаг снят, "
                   "судья: %s)" % в)
        итог["перекинуто" if ок else "решение не легло"] += 1
        if ок:
            поток.write(json.dumps({"review": rid_, "email": r["email"],
                                    "flagi": sorted(коды)},
                                   ensure_ascii=False) + "\n")
            поток.flush(); os.fsync(поток.fileno())
    except Exception as ex:                                      # noqa: BLE001
        итог["ошибка: " + str(ex)[:40]] += 1
if поток:
    поток.close()
print("")
for к, n in итог.most_common():
    print("   %-48s %4d" % (к, n))
