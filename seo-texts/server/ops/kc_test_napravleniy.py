# -*- coding: utf-8 -*-
"""Проверка без отправки: ящики КЦ не могут обслужить письма Meyer (и наоборот).

Собираем стек как служба (wiring.build_deps, dry_run=True — ничего не шлёт) и по
реальным карточкам очереди кампании Meyer проверяем все пути выбора ящика:
send_as (карточка), pick_mailbox (автоотправка), _fallback_mailbox (ответ с
ящиком КЦ в ветке), set_mailbox (ручной выбор — должен отказать, НИЧЕГО не
пишет при отказе), division_block (последний рубеж перед SMTP). Только чтение.
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.wiring import build_deps  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
d = build_deps(cfg, store, dry_run=True)
cs, snd = d.confirm, d.sender
kc = [m.mailbox_id for m in cfg.mailboxes() if getattr(m, "division", None) == "kc"]
me = {m.mailbox_id for m in cfg.mailboxes() if getattr(m, "division", None) == "meyer"}
print("ящиков kc %d, meyer %d; индекс направлений активен: %s" % (len(kc), len(me), getattr(d.cards, "active", None)))
rows = [r for r in cs.pending(limit=100_000) if r.get("campaign_id") == 14][:150]
св = Counter()
for r in rows:
    msg = store.get_message(r["message_id"]) if r.get("message_id") else None
    rec = store.get_recipient(msg.recipient_id) if msg else None
    camp = store.get_campaign(msg.campaign_id) if msg else None
    # 1) карточка
    ch = cs.send_as(r, prefer_division="meyer").get("mailbox_id")
    св["карточка: " + ("kc!!" if ch in kc else "meyer" if ch in me else "нет ящика")] += 1
    # 2) автоотправка
    if rec and camp:
        try:
            pm = snd.pick_mailbox(rec, camp, message=msg)
        except Exception as е:  # noqa: BLE001
            pm = "ошибка:" + type(е).__name__
        св["автоотправка: " + ("kc!!" if pm in kc else "meyer" if pm in me else str(pm)[:20])] += 1
    # 3) ответ, если в ветке ящик КЦ
    fb = cs._fallback_mailbox(inn=r.get("inn"), prefer_mailbox=kc[0], prefer_division="meyer")
    св["ответ из ветки КЦ: " + ("kc!!" if fb in kc else "meyer" if fb in me else "нет ящика")] += 1
    # 4) последний рубеж
    if rec and msg:
        блоки = [snd.division_block(rec, k, message=msg) for k in kc[:5]]
        св["рубеж SMTP для kc-ящика: " + ("ПРОПУСТИЛ!!" if any(b is None for b in блоки) else "блок")] += 1
# 5) ручной выбор ящика КЦ на карточке Meyer — ожидаем отказ (при отказе ничего не пишется)
if rows:
    try:
        cs.set_mailbox(rows[0]["id"], kc[0], operator="test")
        св["ручной выбор kc на Meyer: ПРИНЯТ!! (вернул бы)"] += 1
        # откат на всякий случай
        p = dict(rows[0].get("panel") or {})
        store.confirm_set_panel(rows[0]["id"], p)
    except Exception as е:  # noqa: BLE001
        св["ручной выбор kc на Meyer: отказ (%s)" % type(е).__name__] += 1
print("проверено карточек Meyer: %d" % len(rows))
for к, n in sorted(св.items()):
    print("   %-52s %d" % (к, n))
print("=== ТЕСТ НАПРАВЛЕНИЙ ===")
