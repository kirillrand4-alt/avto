# -*- coding: utf-8 -*-
"""Почему подбор не даёт ящика ни одному из 47 писем.

Разбираем шаг за шагом ровно то, что делает _fallback_mailbox: какие
направления разрешены компании, какие ящики проходят can_send_now у ЖИВОГО
отправителя (им шлёт панель), и какой лимит у каждого по рампе.
"""
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                    # noqa: E402
from sender.ramp import daily_send_limit                            # noqa: E402
from sender.store import Store                                      # noqa: E402
from sender.wiring import build_deps                                # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
cs, живой = deps.confirm, None
живой = getattr(cs, "_sender", None)
сейчас = datetime.now(timezone.utc)
print(f"сейчас UTC {сейчас:%H:%M}; живой отправитель: {живой is not None}\n")

print(f"{'ящик Meyer':<40} {'рамп':>5} {'лимит':>6} {'ушло':>5} {'можно':>7} "
      f"{'гейт ящика'}")
for mb in cfg.mailboxes():
    if mb.division != "meyer":
        continue
    ст = store.get_mailbox_state(mb.mailbox_id)
    рд = getattr(ст, "ramp_day", 0) if ст else 0
    ушло = getattr(ст, "sent_today", 0) if ст else 0
    лим = daily_send_limit(cfg, mb.provider, рд)
    try:
        реальный = живой._daily_limit(mb.provider, рд, mb.mailbox_id)
    except Exception as ex:                                        # noqa: BLE001
        реальный = f"ош:{str(ex)[:20]}"
    можно = живой.can_send_now(mb.mailbox_id, now=сейчас, manual=True)
    try:
        гейт = живой.gates.check_mailbox(mb.mailbox_id)
        гтекст = f"{'СРАБОТАЛ' if гейт.tripped else 'ок'} {getattr(гейт,'reason','') or ''}"
    except Exception as ex:                                        # noqa: BLE001
        гтекст = f"ош: {str(ex)[:40]}"
    print(f"{mb.mailbox_id:<40} {рд:>5} {лим:>3}/{реальный:<3} {ушло:>5} "
          f"{str(можно):>7}  {гтекст[:46]}")

with store._lock:
    кид = store._conn.execute(
        "SELECT id FROM confirm_reviews WHERE dedup_key LIKE 'vebinar28:%' "
        "AND status='pending' ORDER BY id LIMIT 1").fetchone()[0]
строка = cs.get(кид)
print(f"\nразбор на карточке №{кид} ({строка.get('email')}), ИНН {строка.get('inn')}")
cards = cs._cards
активны = getattr(cards, "active", False) if cards else False
print(f"  индекс обзвона активен: {активны}")
if активны:
    try:
        getter = getattr(cards, "divisions", None)
        разрешено = getter(строка.get("inn")) if callable(getter) else None
        if разрешено is None:
            разрешено = cards.division(строка.get("inn"))
        print(f"  разрешённые направления компании: {разрешено}")
    except Exception as ex:                                        # noqa: BLE001
        print(f"  направления компании не прочитались: {str(ex)[:70]}")
print(f"  letter_division: {cs.letter_division(строка)}")
print(f"  _fallback_mailbox -> {cs._fallback_mailbox(inn=строка.get('inn'), prefer_division='meyer')}")
как = cs.send_as(строка, prefer_division="meyer")
print(f"  send_as.chosen -> {как.get('chosen')!r}; ключи: {sorted(как)[:8]}")
