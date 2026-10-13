# -*- coding: utf-8 -*-
"""Спасти письма, забракованные ТОЛЬКО за «нет просьбы перенаправить» (владелец
13.10: «да»). Модель денег не тратит: просьбу вставляем механически
(ai_letter.vstavit_prosbu), письмо прогоняем через тот же механический гейт и
кладём в очередь подтверждения штатным путём (ConfirmSend.submit: стоп-лист,
мёртвый адрес, «отвечали», контакт < 90 дней, квота компании).

Пропускаем: у компании уже есть годное письмо в журнале или письмо в кампании
(в очереди/отправлено); контакт снят книгой MEYER-7 (snyat_knigoy).
Журнал durable: _ops/dolozheno-bez-prosby.jsonl. Без --katit — сухой прогон.

    dolozhit_bez_prosby.py [--katit]
"""
import io
import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import date

sys.path.insert(0, r"C:\sender")
from sender.ai_letter import bez_dlinnogo_tire, gate, load_facts, vstavit_prosbu  # noqa: E402
from sender.ai_quota import build_ai_quota  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.confirm import ConfirmSend  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.suppression import Suppression  # noqa: E402

ЖУРНАЛ = r"C:\sender\_ops\gen-rossiya-9000.jsonl"
СВОЙ = r"C:\sender\_ops\dolozheno-bez-prosby.jsonl"
ПРИЧИНА = "нет просьбы перенаправить письмо ответственному"
КАМПАНИЯ = {"meyer": 14}
КАТИТЬ = "--katit" in sys.argv

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
cs = ConfirmSend(cfg, store, Suppression(store))
_факты = {"meyer": load_facts(division="meyer")}
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)

уже = set()
if os.path.exists(СВОЙ):
    for s in io.open(СВОЙ, encoding="utf-8"):
        уже.add(int(json.loads(s)["recipient_id"]))
записи = [json.loads(s) for s in io.open(ЖУРНАЛ, encoding="utf-8") if s.strip()]
готовые_инн = {str(z.get("inn")) for z in записи if z.get("этап") == "итог" and z.get("ок")}
по_получателю = {}
for z in записи:
    if z.get("этап") == "сгенерировано" and z.get("тело_брака") and [str(x) for x in (z.get("брак") or [])] == [ПРИЧИНА]:
        по_получателю[int(z["recipient_id"])] = z
счёт, работа = Counter(), []
for rid, z in по_получателю.items():
    if rid in уже:
        счёт["уже доложено"] += 1
        continue
    if str(z.get("inn")) in готовые_инн:
        счёт["у компании уже есть годное письмо"] += 1
        continue
    if z.get("направление") not in КАМПАНИЯ:
        счёт["не meyer"] += 1
        continue
    ex = (c.execute("SELECT extra_json FROM recipients WHERE id=?", (rid,)).fetchone() or [""])[0] or ""
    if "snyat_knigoy" in ex:
        счёт["контакт снят книгой"] += 1
        continue
    if c.execute("SELECT 1 FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE r.inn=? AND m.campaign_id=? "
                 "AND m.status IN ('pending_review','approved','scheduled','sending','sent')",
                 (z.get("inn"), КАМПАНИЯ[z["направление"]])).fetchone():
        счёт["письмо в кампании уже есть"] += 1
        continue
    работа.append(z)
print("черновиков только с этой причиной: %d; к докладке: %d; %s" % (len(по_получателю), len(работа), dict(счёт)))
итоги = Counter()
день = date.today().isoformat()
for z in работа:
    rid, inn, div = int(z["recipient_id"]), str(z.get("inn") or ""), z["направление"]
    rec = store.get_recipient(rid)
    if not rec:
        итоги["получателя нет"] += 1
        continue
    тема = bez_dlinnogo_tire(str(z.get("тема_брака") or ""))
    тело = bez_dlinnogo_tire(vstavit_prosbu(str(z.get("тело_брака") or "")))
    try:
        req = q._request(rec)
    except Exception:  # noqa: BLE001
        req = {"mode": "GENERIC", "extra": {}}
    _extra = dict(req.get("extra") or {})
    for k in ("company_name", "contact_name", "city"):
        if not _extra.get(k) and getattr(rec, k, None):
            _extra[k] = getattr(rec, k)
    fails = gate(тема, тело, mode=req.get("mode") or "GENERIC", extra=_extra, facts=_факты[div], division=div)
    строка = {"recipient_id": rid, "inn": inn, "имя": z.get("имя"), "тема": тема, "тело": тело,
              "гейт": [str(f)[:120] for f in (fails or [])[:3]], "день": день}
    if fails:
        итоги["гейт снова забраковал: " + str(fails[0])[:60]] += 1
    elif not КАТИТЬ:
        итоги["чисто, к очереди"] += 1
        if итоги["чисто, к очереди"] <= 2:
            print("--- пример: %s\n%s" % (z.get("имя"), тело[-420:]))
        continue
    else:
        cid = КАМПАНИЯ[div]
        try:
            пара = q._ensure_message(cid, rid)
            mid = пара[0] if пара else None
            panel = q._panel(rec, {"subject": тема, "body": тело}, день, req)
            r = cs.submit(email=str(getattr(rec, "email", "") or ""), subject=тема, body=тело, inn=inn,
                          campaign_id=cid, recipient_id=rid, message_id=mid, panel=panel)
            строка["review_id"] = getattr(r, "review_id", None)
            строка["статус"] = str(getattr(r, "status", ""))
            итоги["в очереди" if строка["статус"] == "pending" else "очередь: " + строка["статус"][:50]] += 1
        except Exception as е:  # noqa: BLE001
            строка["очередь"] = "%s: %s" % (type(е).__name__, str(е)[:110])
            итоги["сбой очереди"] += 1
    if КАТИТЬ:
        with io.open(СВОЙ, "a", encoding="utf-8") as f:
            f.write(json.dumps(строка, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
print("итог: %s" % dict(итоги.most_common()))
print("=== ДОЛОЖИТЬ БЕЗ ПРОСЬБЫ: %s ===" % ("КАТИМ" if КАТИТЬ else "сухой прогон"))
