# -*- coding: utf-8 -*-
"""Письма на следующий адрес лесенки — в «Подтвердить отправку» (владелец
23.10: «поставь такое же письмо, как уже было отправлено этой компании на
первый адрес, на второй адрес по лесенке и закинь в подтвердить отправку»).

Вход — _ops/lesenka-<id>.json (lesenka_kampanii.py <id> --s-hr). Для каждой
компании: последнее отправленное ей письмо кампании <id> (тема, текст до
«С уважением,», ящик); обращение по имени («Иван, добрый день!») меняем на
«Добрый день!». Получатель — на новый адрес (карточка прошлого получателя без
имени контакта), сообщение в кампании «Второе касание — Meyer» (13), карточка
штатным ConfirmSend.submit; panel.kopiya_s — прошлый адрес, mailbox_id — ящик
первого письма. Правило отправки: другой адрес той же компании — через 3 дня
(lesenka_3dnya.py). Журнал _ops/lesenka-ochered-<id>.jsonl (повтор не ставит).
    lesenka_v_ochered.py <id> [--klast]"""
import io
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota         # noqa: E402
from sender.config import Config                   # noqa: E402
from sender.confirm import ConfirmSend             # noqa: E402
from sender.store import Store                     # noqa: E402
from sender.suppression import Suppression         # noqa: E402

cid = int(sys.argv[1])
КАМП = 13
ЖУР = r"C:\sender\_ops\lesenka-ochered-%d.jsonl" % cid
КЛАСТЬ = "--klast" in sys.argv
ИМЯ_ЗАЧИН = re.compile(r"^\s*[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){0,2},\s*(добрый день|здравствуйте)[!.]?", re.I)
д = json.load(io.open(r"C:\sender\_ops\lesenka-%d.json" % cid, encoding="utf-8"))
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
сделано = set()
if os.path.exists(ЖУР):
    сделано = {json.loads(s).get("inn") for s in io.open(ЖУР, encoding="utf-8")}
сч = Counter()
план = []
# --tolko-vtoroe (владелец 26.10: «реальное второе (не больше) касание»):
# компании, у которой Meyer уже писал на 2+ адреса, третье не ставим.
ТОЛЬКО_ВТОРОЕ = "--tolko-vtoroe" in sys.argv
_мей = [r[0] for r in c.execute("SELECT id, name FROM campaigns") if "meyer" in str(r[1]).lower()]
# компании пилота напоминаний 26.10 только что получили «Re:» — второй адрес им пока не шлём
_пилот = set()
if os.path.exists(r"C:\sender\_ops\napominaniya-pilot.jsonl"):
    _пилот = {json.loads(s).get("inn") for s in io.open(r"C:\sender\_ops\napominaniya-pilot.jsonl", encoding="utf-8")}
for x in д:
    if x["inn"] in _пилот:
        сч["в пилоте напоминаний — пока нет"] += 1
        continue
    if x["inn"] in сделано:
        сч["уже ставили"] += 1
        continue
    if ТОЛЬКО_ВТОРОЕ:
        n_адр = c.execute("SELECT COUNT(DISTINCT lower(r.email)) FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                          "WHERE r.inn=? AND m.campaign_id IN (%s) AND m.status IN ('sent','scheduled','sending','pending_review')"
                          % ",".join(map(str, _мей)), (x["inn"],)).fetchone()[0]
        if n_адр >= 2:
            сч["уже 2+ адреса — не третье"] += 1
            continue
    р = c.execute("SELECT m.id mid, m.mailbox_id mb, r.id rid, lower(r.email) em, cr.subject, cr.body FROM messages m "
                  "JOIN recipients r ON r.id=m.recipient_id LEFT JOIN confirm_reviews cr ON cr.message_id=m.id "
                  "WHERE m.campaign_id=? AND m.status='sent' AND r.inn=? ORDER BY m.sent_at DESC LIMIT 1",
                  (cid, x["inn"])).fetchone()
    if not р or not р["body"]:
        сч["нет текста первого письма"] += 1
        continue
    тело = str(р["body"]).split("\n\nС уважением,")[0].rstrip()
    if ИМЯ_ЗАЧИН.search(тело):
        тело = ИМЯ_ЗАЧИН.sub("Добрый день!", тело, count=1)
        сч["обращение по имени заменено"] += 1
    if re.search(r"(?i)\bвам как\b", тело):
        сч["в тексте «вам как …» (оставлено)"] += 1
    план.append((x, р, тело))
print("в списке:", len(д), "| к постановке:", len(план), dict(сч))
if not КЛАСТЬ:
    for x, р, тело in план[:2]:
        print("\n-> %s (было %s, ящик %s)\nТема: %s\n%s" % (x["email"], р["em"], р["mb"], р["subject"], тело[:400]))
    print("\nСУХОЙ ПРОГОН. Класть — --klast")
    sys.exit()
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
cs = ConfirmSend(cfg, store, Suppression(store))
# ящик первого письма мог уйти из конфига (август: zernosort.ru и др.) — тогда
# ящик не задаём, панель подберёт рабочий ящик Meyer сама
_ящики = {mb.mailbox_id for mb in cfg.mailboxes() if mb.division == "meyer"}
итог = Counter()
ж = io.open(ЖУР, "a", encoding="utf-8")
for x, р, тело in план:
    адр = x["email"]
    п = c.execute("SELECT * FROM recipients WHERE id=?", (р["rid"],)).fetchone()
    есть = c.execute("SELECT id FROM recipients WHERE lower(email)=?", (адр,)).fetchone()
    if есть:
        rid = есть[0]
    else:
        теперь = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        ex = json.loads((п["extra_json"] if п else None) or "{}")
        ex.update({"vtoroe_kasanie_s": р["em"], "rol_vtorogo": x.get("role"), "lesenka_iz_kampanii": cid})
        with c:
            cur = c.execute("INSERT INTO recipients (inn,email,domain,company_name,okved,segment,contact_name,source,region,"
                            "extra_json,tz,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (x["inn"], адр, адр.split("@")[-1], п["company_name"] if п else None, п["okved"] if п else None,
                             (п["segment"] if п else None) or "meyer", None, "lesenka-2310",
                             п["region"] if п else None, json.dumps(ex, ensure_ascii=False),
                             п["tz"] if п else None, теперь, теперь))
            rid = cur.lastrowid
    mid, _шаг, почему = q._ensure_message(КАМП, int(rid))
    if not mid:
        итог["сообщение не завелось: " + str(почему)[:40]] += 1
        continue
    r = cs.submit(email=адр, subject=р["subject"], body=тело + "\n\nС уважением,", inn=x["inn"], campaign_id=КАМП,
                  recipient_id=rid, message_id=mid,
                  panel=dict({"letter_division": "meyer", "kopiya_s": р["em"], "vtoroe_kasanie": True,
                              "lesenka_iz_kampanii": cid},
                             **({"mailbox_id": р["mb"]} if р["mb"] in _ящики else {})))
    if р["mb"] not in _ящики:
        итог["ящик первого письма не в работе — подберёт панель"] += 1
    итог["очередь: " + str(r.status) + ((" " + str(r.reason)[:50]) if getattr(r, "reason", None) else "")] += 1
    ж.write(json.dumps({"inn": x["inn"], "кому": адр, "review": r.review_id, "status": r.status}, ensure_ascii=False) + "\n")
    ж.flush()
    os.fsync(ж.fileno())
print("ИТОГ:", dict(итог.most_common()))
