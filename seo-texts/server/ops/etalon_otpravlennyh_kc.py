# -*- coding: utf-8 -*-
"""Что было в ОТПРАВЛЕННЫХ письмах КЦ - эталон, а не мои догадки.

Владелец: «нужно то что было в тех письмах, они были согласованы». Значит
спор о правилах решается не рассуждением, а долей в письмах со статусом
sent/approved: их читал и одобрял человек.

Замер по свежей партии показал две дыры разом: у 29% писем КЦ нет строки
отказа, и у 94% нет просьбы перенаправить, хотя правило «нет имени - проси
перенаправить» мы вводили. Прежде чем чинить, сверяемся с эталоном: было ли
это в согласованных письмах и в какой доле.

    python zapusk_svoego_skripta.py ops/etalon_otpravlennyh_kc.py
"""
import json
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.ai_letter import (_imennoe_privetstvie,             # noqa: E402
                              _prosba_perenapravit)
from sender.confirm import ConfirmSend                          # noqa: E402
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.suppression import Suppression                      # noqa: E402

ОТКАЗ = "в дальнейшем вас не отвлекать"
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))

with store._lock:
    строки = store._conn.execute(
        "SELECT id, campaign_id, email, subject, body, panel_json, status "
        "FROM confirm_reviews WHERE status IN ('sent','approved') "
        "ORDER BY id").fetchall()

счёт = Counter()
примеры = []
for rid, camp, email, subj, body, pj, статус in строки:
    body = str(body or "")
    if not body.strip():
        счёт["тела нет (только тема)"] += 1
        continue
    try:
        panel = json.loads(pj or "{}")
    except Exception:                                           # noqa: BLE001
        panel = {}
    r = {"subject": subj, "body": body, "panel": panel}
    напр = str(cs.letter_division(r) or "")
    if напр != "kc":
        счёт[f"пропущено: направление {напр or '?'}"] += 1
        continue
    счёт["писем КЦ отправлено/одобрено"] += 1
    счёт["строка отказа есть" if ОТКАЗ in body
         else "строки отказа нет"] += 1
    по_имени = _imennoe_privetstvie(body)
    просьба = _prosba_perenapravit(body)
    счёт["именное приветствие" if по_имени else "безличное"] += 1
    счёт["просьба перенаправить есть" if просьба else "просьбы нет"] += 1
    if не := (по_имени and просьба):
        счёт["и имя, и просьба разом"] += 1
    if not по_имени:
        счёт["безличное: просьба есть" if просьба
             else "безличное: просьбы НЕТ"] += 1
    if просьба and len(примеры) < 6:
        м = re.search(r'(?i)[^.\n]*(перенаправ|передайте|адресова|'
                      r'не по адресу)[^.\n]*\.', body)
        if м:
            примеры.append(f"#{rid}: {м.group(0).strip()[:120]}")

всего = max(1, счёт["писем КЦ отправлено/одобрено"])
print(f"эталон: писем КЦ со статусом sent/approved - {всего}")
for k, n in счёт.most_common():
    print(f"  {k:<40} {n:>4}  {100.0 * n / всего:.0f}%")
print("\nкак просьба звучала в согласованных письмах:")
for s in примеры:
    print(f"  {s}")
