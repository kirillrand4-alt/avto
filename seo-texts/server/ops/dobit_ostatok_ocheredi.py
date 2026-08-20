# -*- coding: utf-8 -*-
"""Хвост очереди: дубли на тот же адрес - снять, новые компании - в отправку.

Дубль это когда письмо идёт на адрес, куда мы этой же компании уже
писали. Копия (другой адрес той же компании) разобрана отдельно и уже
ушла с обращением по имени.
"""
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.auto_send import (next_slot, recipient_tz_name,      # noqa: E402
                              window_from)
from sender.config import Config                                 # noqa: E402
from sender.confirm import ConfirmSend                           # noqa: E402
from sender.store import Store                                   # noqa: E402
from sender.suppression import Suppression                       # noqa: E402

КАТИТЬ = "--katit" in sys.argv
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))
окно = window_from(store, cfg)
сейчас = datetime.now(timezone.utc)
АДР = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Zа-яА-Я]{2,}$")

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT cr.id, cr.email, cr.message_id, cr.recipient_id, r.inn, "
    "       r.company_name, COALESCE(p.verdict,'') proba "
    "FROM confirm_reviews cr LEFT JOIN recipients r ON r.id=cr.recipient_id "
    "LEFT JOIN addr_probe p ON p.email=lower(cr.email) "
    "WHERE cr.status='pending' ORDER BY cr.id").fetchall()

дубли, свежие = [], []
счёт = Counter()
for r in ряды:
    инн = "".join(ch for ch in str(r["inn"] or "") if ch.isdigit())
    почта = str(r["email"] or "").strip().lower()
    адреса = {str(x[0] or "").lower() for x in c.execute(
        "SELECT email FROM send_log WHERE inn=?", (инн,))} if инн else set()
    if почта in адреса:
        дубли.append((r, "этому адресу уже писали"))
        счёт["ДУБЛЬ: снять"] += 1
        continue
    if адреса:
        счёт["копия (разобрана отдельно)"] += 1
        continue
    плохо = []
    if not АДР.match(почта):
        плохо.append("формат адреса")
    if str(r["proba"]) in ("нет ящика", "нет MX"):
        плохо.append(f"приговор пробы: {r['proba']}")
    try:
        п = cs._guard(inn=инн, email=почта)
        if п:
            плохо.append(f"заслон: {п.split(':')[0]}")
    except Exception as ex:                                      # noqa: BLE001
        плохо.append(f"заслон не отработал: {str(ex)[:40]}")
    if плохо:
        for x in плохо:
            счёт[f"не проходит: {x}"] += 1
        continue
    свежие.append(r)
    счёт["новая компания: в отправку"] += 1

print(f"в очереди: {len(ряды)}")
for k, n in счёт.most_common():
    print(f"  {n:>4}  {k}")
for r, _ in дубли[:20]:
    print(f"    дубль #{r['id']} {str(r['company_name'])[:34]:<34} {r['email']}")

if not КАТИТЬ:
    print("\nсухой прогон. Катить - --katit")
    raise SystemExit(0)

снято = одобрено = 0
for r, причина in дубли:
    try:
        if store.confirm_decide(int(r["id"]), status="skipped",
                                reason=причина,
                                decided_by="разбор хвоста 20.08") is not False:
            снято += 1
    except Exception as ex:                                      # noqa: BLE001
        print(f"  #{r['id']} не снялось: {str(ex)[:80]}")
for r in свежие:
    try:
        if store.confirm_decide(int(r["id"]), status="approved",
                                decided_by="разбор хвоста 20.08") is False:
            continue
        одобрено += 1
        rec = store.get_recipient(r["recipient_id"])
        if r["message_id"] and rec is not None:
            store.reschedule_message(
                int(r["message_id"]),
                next_slot(окно, recipient_tz_name(окно, rec), сейчас))
    except Exception as ex:                                      # noqa: BLE001
        print(f"  #{r['id']} не одобрилось: {str(ex)[:80]}")
print(f"\nснято дублей: {снято} | в отправку: {одобрено}")
