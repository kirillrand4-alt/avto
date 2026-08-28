# -*- coding: utf-8 -*-
"""Разобрать «поправить» обеих партий: косметику и среднее — в автоотправку,
критичное — снять и вернуть в генерацию.

Владелец 28.08: «давай всё что предложил».

Критичное — письмо рассказывает адресату про его же цех то, чего там нет
(«приписаны покрасочные камеры и пескоструй»). Косметика — склонение
названия: некрасиво, но это не ложь. «Неясно» кладём к критичному: его
примеры — те же домыслы без опоры на карточку.

    razobrat_popravit.py [--katit]
"""
import io
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
sys.path.insert(1, r"C:\sender\sender")
КАТИТЬ = "--katit" in sys.argv
ГРУППА = "peregen2"
СЛЕД_ПЕР = r"C:\sender\_ops\v-avtootpravku-popravit.jsonl"
СЛЕД_СНЯТ = r"C:\sender\_ops\snyato-kriticheskih.jsonl"

всё = {}
for ф, п in ((r"C:\sender\_ops\sud-vtoryh.jsonl", 1),
             (r"C:\sender\_ops\sud-vtoryh-2.jsonl", 2)):
    try:
        for с in io.open(ф, encoding="utf-8"):
            d = json.loads(с)
            всё[int(d["id"])] = d
    except FileNotFoundError:
        pass
поправ = {i: d for i, d in всё.items()
          if str(d.get("verdikt") or "").replace("o", "о").replace("p", "р") == "поправить"}
КРИТ = re.compile(r"(?i)(выдум|придума|не подтвержд|нет в карточке|нет данных|"
                  r"перепута|не производ|не занимается|которых нет|которой нет|"
                  r"ошибочн|неверн[оыа]|не соответству|приписан|домысел|догадк)")
СРЕДН = re.compile(r"(?i)(реклам|обеща|навязчив|обращени|не тому|чужому|роль|адресат)")
КОСМ = re.compile(r"(?i)(склонени|падеж|формулиров|коряв|стилист|опечат|запят|громоздк)")

критичные, слать = [], []
for i, d in поправ.items():
    т = str(d.get("chto_ne_tak") or "")
    if str(d.get("vydumka") or "").strip() or d.get("fakty_verny") is False or КРИТ.search(т):
        критичные.append(i)
    elif (d.get("obrashchenie_ok") is False or d.get("reklama") is True
          or СРЕДН.search(т) or d.get("yazyk_ok") is False or КОСМ.search(т)):
        слать.append(i)
    else:
        критичные.append(i)          # «неясно» — те же домыслы
print("«поправить»: %d | критичных (снять+перегенерить): %d | слать: %d"
      % (len(поправ), len(критичные), len(слать)))

from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.wiring import build_deps                              # noqa: E402
from sender.auto_send import next_slot, recipient_tz_name, window_from  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = build_deps(cfg, store, dry_run=True).confirm
win = window_from(store, cfg)
now = datetime.now(timezone.utc)

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row


def живые(ids):
    if not ids:
        return []
    зн = ",".join("?" * len(ids))
    return c.execute(
        "SELECT id, inn, email, recipient_id, message_id, panel_json "
        "  FROM confirm_reviews WHERE id IN (%s) AND status='pending'" % зн,
        ids).fetchall()


ж_слать, ж_крит = живые(слать), живые(критичные)
c.close()
print("в очереди: слать %d, критичных %d" % (len(ж_слать), len(ж_крит)))
if not КАТИТЬ:
    raise SystemExit(0)

# --- 1. косметику и среднее в автоотправку ---
итог = Counter()
поток = io.open(СЛЕД_ПЕР, "a", encoding="utf-8")
for r in ж_слать:
    try:
        панель = json.loads(r["panel_json"] or "{}") or {}
    except Exception:                                            # noqa: BLE001
        панель = {}
    if ((панель.get("actions") or {}).get("confirm_hold")):
        итог["стоп-флаг карточки"] += 1
        continue
    блок = None
    try:
        блок = cs._guard(inn=r["inn"], email=r["email"] or "")
    except Exception:                                            # noqa: BLE001
        блок = None
    if блок:
        итог["заслон: " + str(блок)[:36]] += 1
        continue
    rec = store.get_recipient(int(r["recipient_id"])) if r["recipient_id"] else None
    if rec is None or r["message_id"] is None:
        итог["нет получателя/письма"] += 1
        continue
    try:
        слот = next_slot(win, recipient_tz_name(win, rec), now)
        store.reschedule_message(int(r["message_id"]), слот)
        ок = store.confirm_decide(
            int(r["id"]), status="approved", decided_by="партия вторых адресов",
            reason="bulk-to-auto: копия на второй адрес (судья: поправить, "
                   "огрехи косметические)")
        итог["переведено" if ок else "решение не легло"] += 1
        if ок:
            поток.write(json.dumps({"review": int(r["id"]), "email": r["email"],
                                    "slot": str(слот)}, ensure_ascii=False) + "\n")
            поток.flush(); os.fsync(поток.fileno())
    except Exception as ex:                                      # noqa: BLE001
        итог["ошибка перевода: " + str(ex)[:36]] += 1
поток.close()

# --- 2. критичные снять и вернуть в генерацию ---
поток2 = io.open(СЛЕД_СНЯТ, "a", encoding="utf-8")
for r in ж_крит:
    почему = str(поправ[int(r["id"])].get("chto_ne_tak") or "")[:150]
    try:
        ок = cs.skip(int(r["id"]),
                     reason="судья писем: выдуманная конкретика — " + почему,
                     operator="разбор поправить 28.08")
        итог["снято критичных" if ок else "не снялось"] += 1
        if not ок:
            continue
        поток2.write(json.dumps({"review": int(r["id"]), "inn": r["inn"],
                                 "email": r["email"], "prichina": почему},
                                ensure_ascii=False) + "\n")
        поток2.flush(); os.fsync(поток2.fileno())
        if r["recipient_id"]:
            with store.transaction() as conn:
                row = conn.execute("SELECT extra_json FROM recipients WHERE id=?",
                                   (int(r["recipient_id"]),)).fetchone()
                ex_ = json.loads((row[0] if row else None) or "{}") or {}
                гр = list(ex_.get("gruppy") or [])
                if ГРУППА not in гр:
                    гр.append(ГРУППА)
                    ex_["gruppy"] = гр
                    conn.execute(
                        "UPDATE recipients SET extra_json=?, updated_at=? WHERE id=?",
                        (json.dumps(ex_, ensure_ascii=False),
                         time.strftime("%Y-%m-%dT%H:%M:%S"), int(r["recipient_id"])))
                    итог["в группу " + ГРУППА] += 1
    except Exception as ex:                                      # noqa: BLE001
        итог["ошибка снятия: " + str(ex)[:36]] += 1
поток2.close()
print("")
for к, n in итог.most_common():
    print("   %-44s %5d" % (к, n))
