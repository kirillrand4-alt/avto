# -*- coding: utf-8 -*-
"""Что мешает каждому ОСТАВШЕМУСЯ письму уйти прямо сейчас.

Важно не путать две очереди. confirm_reviews.status='approved' остаётся
'approved' и ПОСЛЕ отправки — это отметка оператора, а не очередь. Реальная
очередь живёт в messages.status='scheduled'. Здесь берём именно её и по
каждому письму спрашиваем подбор ящика, почему он ничего не дал.

    python zapusk_svoego_skripta.py ops/chto_meshaet_ostatku.py
"""
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402
from sender.wiring import build_deps                             # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
snd = deps.sender
сейчас = datetime.now(timezone.utc)
маршрут = cfg.get("provider_split.routing", {}) or {}

with store._lock:
    ряд = store._conn.execute(
        "SELECT m.id, m.campaign_id, m.recipient_id, m.scheduled_at, "
        "       COALESCE(r.mx_provider,'unknown'), COALESCE(r.tz,''), r.email "
        "FROM messages m LEFT JOIN recipients r ON r.id=m.recipient_id "
        "WHERE m.status='scheduled' ORDER BY m.scheduled_at").fetchall()
print(f"в очереди (messages.status='scheduled'): {len(ряд)}")

пора = [x for x in ряд if str(x[3] or "") <= сейчас.isoformat()]
позже = [x for x in ряд if str(x[3] or "") > сейчас.isoformat()]
print(f"  срок настал: {len(пора)} | ждут слота: {len(позже)}\n")

классы = {c.id: c for c in (store.list_campaigns() if hasattr(
    store, "list_campaigns") else [])}
причины = Counter()
примеры = {}
for mid, cid, rid, ts, пров, tz, email in пора:
    r = store.get_recipient(int(rid)) if rid else None
    камп = классы.get(cid)
    if камп is None:
        try:
            камп = store.get_campaign(int(cid))
        except Exception:                                        # noqa: BLE001
            камп = None
    пул = маршрут.get(str(пров).lower()) or маршрут.get("other") or "?"

    class _M:
        id = mid
    выбран = None
    try:
        выбран = snd.pick_mailbox(r, камп, now=сейчас, message=_M())
    except Exception as ex:                                      # noqa: BLE001
        причины[f"подбор упал: {type(ex).__name__} {str(ex)[:60]}"] += 1
        continue
    if выбран:
        причины[f"МОЖЕТ уйти -> {выбран}"] += 1
        continue
    # разбираем, почему пул пуст
    ящики = cfg.provider_pools().get(пул, [])
    свои = Counter()
    for mb in ящики:
        д = snd.division_block(r, mb, message=_M())
        if д is not None:
            свои[д.split(":")[0]] += 1
            continue
        rd = snd.mailbox_readiness(mb)
        if not snd.can_send_now(mb, now=сейчас):
            свои[",".join(rd.reasons) or "пейсинг/квота"] += 1
    ключ = f"{пул}: " + "; ".join(f"{k}×{v}" for k, v in свои.most_common(3))
    причины[ключ] += 1
    примеры.setdefault(ключ, (mid, email, tz))

print("почему стоят письма, чей срок настал:")
for п, n in причины.most_common():
    пр = примеры.get(п)
    хвост = f"   напр. письмо {пр[0]} {пр[1]} {pr2}" if (pr2 := (пр[2] if пр else "")) else (
        f"   напр. письмо {пр[0]} {пр[1]}" if пр else "")
    print(f"  {n:>4}  {п}{хвост}")

with store._lock:
    сбои = store._conn.execute(
        "SELECT id, last_error FROM messages WHERE status='failed' "
        "ORDER BY updated_at DESC LIMIT 5").fetchall()
if сбои:
    print("\nпоследние failed:")
    for i, e in сбои:
        print(f"  {i}: {str(e)[:120]}")
